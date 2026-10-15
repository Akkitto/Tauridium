//! Exercise the security backport with optimization, not only source assertions.
#[cfg(all(test, target_os = "linux"))]
mod tests {
    use gtk::glib::variant::ToVariant;

    #[test]
    fn variant_string_iterators_preserve_c_out_parameter_writes() {
        let value = ["first", "second", "third", "last"].to_variant();
        assert_eq!(value.array_iter_str().unwrap().next(), Some("first"));
        assert_eq!(value.array_iter_str().unwrap().nth(2), Some("third"));
        assert_eq!(value.array_iter_str().unwrap().last(), Some("last"));
        assert_eq!(value.array_iter_str().unwrap().next_back(), Some("last"));
        assert_eq!(value.array_iter_str().unwrap().nth_back(2), Some("second"));
    }
}
