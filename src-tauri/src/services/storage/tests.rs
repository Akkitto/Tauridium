use super::*;

#[test]
fn shared_sandbox_storage_identifier_is_stable_and_distinct() {
    let isolated = storage_identifier("00112233-4455-6677-8899-aabbccddeeff", None).unwrap();
    let shared_a = storage_identifier("service-a", Some("proton")).unwrap();
    let shared_b = storage_identifier("service-b", Some("proton")).unwrap();
    let other = storage_identifier("service-a", Some("other")).unwrap();
    assert_eq!(shared_a, shared_b);
    assert_ne!(shared_a, isolated);
    assert_ne!(shared_a, other);
}
#[test]
fn shared_sandbox_storage_is_stable_and_distinct_from_isolated_storage() {
    let root = Path::new("/tmp/tauridium-test");
    let isolated = storage_directory(root, "service-a", None).unwrap();
    let shared_a = storage_directory(root, "service-a", Some("proton")).unwrap();
    let shared_b = storage_directory(root, "service-b", Some("proton")).unwrap();
    let other = storage_directory(root, "service-a", Some("other")).unwrap();
    assert_eq!(isolated, root.join("sessions").join("service-a"));
    assert_eq!(shared_a, shared_b);
    assert_ne!(shared_a, isolated);
    assert_ne!(shared_a, other);
    assert!(shared_a
        .file_name()
        .unwrap()
        .to_string_lossy()
        .starts_with("sandbox-"));
}
#[test]
fn uuid_to_bytes_parses_valid_and_rejects_bad() {
    let b = uuid_to_bytes("00112233-4455-6677-8899-aabbccddeeff").unwrap();
    assert_eq!(b[0], 0x00);
    assert_eq!(b[1], 0x11);
    assert_eq!(b[15], 0xff);
    // 32 hexadecimal characters without hyphens are accepted too.
    assert!(uuid_to_bytes("00112233445566778899aabbccddeeff").is_some());
    // wrong length / invalid hexadecimal.
    assert!(uuid_to_bytes("abc").is_none());
    assert!(uuid_to_bytes("zz112233-4455-6677-8899-aabbccddeeff").is_none());
}
