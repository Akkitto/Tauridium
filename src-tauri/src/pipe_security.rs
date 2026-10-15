//! Poll before every synchronous read; never request unavailable bytes.
use std::time::{Duration, Instant};

pub(crate) fn read_exact_until(
    buffer: &mut [u8],
    deadline: Instant,
    mut available: impl FnMut() -> Result<usize, String>,
    mut read: impl FnMut(&mut [u8]) -> Result<usize, String>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < buffer.len() {
        if Instant::now() >= deadline {
            return Err("Tauridium activation pipe read exceeded its deadline".into());
        }
        let count = available()?.min(buffer.len() - offset);
        if count == 0 {
            std::thread::sleep(Duration::from_millis(10));
            continue;
        }
        let received = read(&mut buffer[offset..offset + count])?;
        if received == 0 || received > count {
            return Err(
                "Tauridium activation pipe closed or returned an invalid byte count".into(),
            );
        }
        offset += received;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn a_connected_silent_peer_times_out_without_a_blocking_read() {
        let started = Instant::now();
        let result = read_exact_until(
            &mut [0; 4],
            started + Duration::from_millis(15),
            || Ok(0),
            |_| panic!("must not read unavailable bytes"),
        );
        assert!(result.unwrap_err().contains("deadline"));
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn fragmented_peer_never_causes_a_read_larger_than_available_data() {
        let index = Cell::new(0_u8);
        let mut buffer = [0; 4];
        read_exact_until(
            &mut buffer,
            Instant::now() + Duration::from_secs(1),
            || Ok(1),
            |slice| {
                assert_eq!(slice.len(), 1);
                index.set(index.get() + 1);
                slice[0] = index.get();
                Ok(1)
            },
        )
        .unwrap();
        assert_eq!(buffer, [1, 2, 3, 4]);
    }

    #[test]
    fn closed_peer_and_backend_errors_are_reported() {
        let deadline = Instant::now() + Duration::from_secs(1);
        assert!(read_exact_until(&mut [0], deadline, || Ok(1), |_| Ok(0)).is_err());
        assert_eq!(
            read_exact_until(
                &mut [0],
                deadline,
                || Err("synthetic failure".into()),
                |_| unreachable!()
            )
            .unwrap_err(),
            "synthetic failure"
        );
    }
}
