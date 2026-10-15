//! Native limits remain authoritative even when a website replaces the JS shim.
use std::collections::VecDeque;
use std::time::{Duration, Instant};

#[derive(Default)]
pub(crate) struct Budget(VecDeque<(String, Instant)>);

impl Budget {
    pub(crate) fn allow(&mut self, service: &str, now: Instant) -> bool {
        self.0
            .retain(|(_, at)| now.saturating_duration_since(*at) < Duration::from_secs(10));
        if self.0.len() >= 8 || self.0.iter().filter(|(id, _)| id == service).count() >= 2 {
            return false;
        }
        self.0.push_back((service.to_string(), now));
        true
    }
}

pub(crate) fn text(value: &str, limit: usize) -> String {
    value
        .chars()
        .filter(|c| {
            !c.is_control()
                && !matches!(c,
        '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
        })
        .take(limit)
        .collect::<String>()
        .trim()
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn independent_per_service_and_global_budgets_expire_and_stay_bounded() {
        let now = Instant::now();
        let mut budget = Budget::default();
        assert!(budget.allow("mail", now));
        assert!(budget.allow("mail", now));
        assert!(!budget.allow("mail", now));
        for id in ["a", "b", "c", "d", "e", "f"] {
            assert!(budget.allow(id, now));
        }
        assert!(!budget.allow("g", now));
        assert_eq!(budget.0.len(), 8);
        assert!(budget.allow("mail", now + Duration::from_secs(10)));
        assert_eq!(budget.0.len(), 1);
    }

    #[test]
    fn untrusted_notification_text_cannot_inject_controls_or_unbounded_bodies() {
        assert_eq!(text("  Mail\u{202e}\0\n\t title  ", 160), "Mail title");
        assert_eq!(text(&"🙂".repeat(1000), 160).chars().count(), 160);
    }
}
