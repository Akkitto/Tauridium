//! Bound native HTTP memory and forbid transport-security downgrade redirects.
use reqwest::{redirect, Response};
use serde::de::DeserializeOwned;
use tauri::Url;

pub(crate) const MAX_API_BYTES: usize = 16 * 1024 * 1024;
pub(crate) const MAX_RECIPE_BYTES: usize = 1024 * 1024;
static ASSET_READS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(8);

fn redirect_allowed(previous: &[Url], next: &Url) -> bool {
    previous.len() < 10
        && matches!(next.scheme(), "http" | "https")
        && !(previous.iter().any(|url| url.scheme() == "https") && next.scheme() != "https")
}

pub(crate) fn redirect_policy() -> redirect::Policy {
    redirect::Policy::custom(|attempt| {
        if redirect_allowed(attempt.previous(), attempt.url()) {
            attempt.follow()
        } else {
            attempt.error("HTTP redirect exceeds its limit or downgrades secure transport")
        }
    })
}

pub(crate) async fn bytes(mut response: Response, limit: usize) -> Result<Vec<u8>, String> {
    if response
        .content_length()
        .is_some_and(|size| size > limit as u64)
    {
        return Err("HTTP response exceeds its byte budget".into());
    }
    // Bound parallel icon/HTML/script allocations without making login/API
    // responses wait behind slow optional asset servers.
    let _permit = if limit <= MAX_RECIPE_BYTES {
        Some(
            ASSET_READS
                .acquire()
                .await
                .map_err(|_| "HTTP asset scheduler is unavailable")?,
        )
    } else {
        None
    };
    let mut result = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|error| {
        format!(
            "Unable to read HTTP response: {}",
            crate::privacy::text(&error.to_string())
        )
    })? {
        if chunk.len() > limit.saturating_sub(result.len()) {
            return Err("HTTP response exceeds its byte budget".into());
        }
        result.extend_from_slice(&chunk);
    }
    Ok(result)
}

pub(crate) async fn text(response: Response, limit: usize) -> Result<String, String> {
    String::from_utf8(bytes(response, limit).await?)
        .map_err(|_| "HTTP text response is not valid UTF-8".into())
}

pub(crate) async fn json<T: DeserializeOwned>(response: Response) -> Result<T, String> {
    serde_json::from_slice(&bytes(response, MAX_API_BYTES).await?).map_err(|error| {
        // Avoid persisting/returning a server-controlled invalid value through
        // serde's diagnostic; line/column is sufficient to identify bad JSON.
        format!(
            "Invalid HTTP JSON response at line {}, column {}",
            error.line(),
            error.column()
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    fn response(body: &'static [u8]) -> Response {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        std::thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                .unwrap();
            let mut request = Vec::new();
            let mut buffer = [0u8; 512];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = socket.read(&mut buffer).unwrap();
                assert!(count > 0 && request.len() < 8192);
                request.extend_from_slice(&buffer[..count]);
            }
            socket.write_all(body).unwrap();
        });
        tauri::async_runtime::block_on(
            reqwest::Client::new()
                .get(format!("http://{address}/fixture"))
                .send(),
        )
        .unwrap()
    }

    #[test]
    fn unknown_length_and_chunked_bodies_stop_at_the_budget() {
        for body in [
            &b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n123456789"[..],
            &b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n12345\r\n4\r\n6789\r\n0\r\n\r\n"[..],
            &b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\n123456789"[..],
        ] {
            assert!(tauri::async_runtime::block_on(bytes(response(body), 8)).is_err());
        }
        let body = response(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n12345678");
        assert_eq!(
            tauri::async_runtime::block_on(bytes(body, 8)).unwrap(),
            b"12345678"
        );
    }

    #[test]
    fn redirects_preserve_https_and_have_a_finite_hop_limit() {
        let https = Url::parse("https://example.test/").unwrap();
        let http = Url::parse("http://localhost:8000/").unwrap();
        assert!(!redirect_allowed(std::slice::from_ref(&https), &http));
        assert!(redirect_allowed(std::slice::from_ref(&http), &https));
        assert!(!redirect_allowed(&vec![https.clone(); 10], &https));
    }
}
