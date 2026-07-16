//! DB-free unit tests for query-parameter parsing.

use chrono::NaiveDate;
use corridor_api::params::{
    parse_date_opt, parse_hex_meters_or, parse_limit, parse_parameter_cd_opt,
    parse_species_id_opt, parse_species_id_or, DEFAULT_LIMIT, MAX_LIMIT,
};

// ---- dates ----------------------------------------------------------------

#[test]
fn date_none_is_ok_none() {
    assert_eq!(parse_date_opt("from", None), Ok(None));
}

#[test]
fn date_empty_is_ok_none() {
    assert_eq!(parse_date_opt("from", Some("")), Ok(None));
    assert_eq!(parse_date_opt("from", Some("   ")), Ok(None));
}

#[test]
fn date_valid_parses() {
    assert_eq!(
        parse_date_opt("from", Some("2026-07-15")),
        Ok(Some(NaiveDate::from_ymd_opt(2026, 7, 15).unwrap()))
    );
}

#[test]
fn date_invalid_errors() {
    assert!(parse_date_opt("from", Some("notadate")).is_err());
    assert!(parse_date_opt("to", Some("2026-13-40")).is_err());
    assert!(parse_date_opt("from", Some("07/15/2026")).is_err());
}

// ---- species_id -----------------------------------------------------------

#[test]
fn species_id_opt_variants() {
    assert_eq!(parse_species_id_opt(None), Ok(None));
    assert_eq!(parse_species_id_opt(Some("")), Ok(None));
    assert_eq!(parse_species_id_opt(Some("1")), Ok(Some(1)));
    assert_eq!(parse_species_id_opt(Some(" 42 ")), Ok(Some(42)));
    assert!(parse_species_id_opt(Some("abc")).is_err());
    assert!(parse_species_id_opt(Some("1.5")).is_err());
}

#[test]
fn species_id_default() {
    assert_eq!(parse_species_id_or(None, 1), Ok(1));
    assert_eq!(parse_species_id_or(Some(""), 1), Ok(1));
    assert_eq!(parse_species_id_or(Some("3"), 1), Ok(3));
    assert!(parse_species_id_or(Some("nope"), 1).is_err());
}

// ---- limit ----------------------------------------------------------------

#[test]
fn limit_defaults_when_absent() {
    assert_eq!(parse_limit(None), Ok(DEFAULT_LIMIT));
    assert_eq!(parse_limit(Some("")), Ok(DEFAULT_LIMIT));
}

#[test]
fn limit_valid_passthrough() {
    assert_eq!(parse_limit(Some("100")), Ok(100));
    assert_eq!(parse_limit(Some(" 250 ")), Ok(250));
}

#[test]
fn limit_caps_at_max() {
    assert_eq!(parse_limit(Some("999999")), Ok(MAX_LIMIT));
    assert_eq!(parse_limit(Some("50000")), Ok(MAX_LIMIT));
    assert_eq!(parse_limit(Some("50001")), Ok(MAX_LIMIT));
}

#[test]
fn limit_rejects_nonpositive_and_nonint() {
    assert!(parse_limit(Some("0")).is_err());
    assert!(parse_limit(Some("-5")).is_err());
    assert!(parse_limit(Some("abc")).is_err());
}

// ---- hex_meters -----------------------------------------------------------

#[test]
fn hex_meters_default_and_parse() {
    assert_eq!(parse_hex_meters_or(None, 2000), Ok(2000));
    assert_eq!(parse_hex_meters_or(Some(""), 2000), Ok(2000));
    assert_eq!(parse_hex_meters_or(Some("500"), 2000), Ok(500));
    assert!(parse_hex_meters_or(Some("0"), 2000).is_err());
    assert!(parse_hex_meters_or(Some("-1"), 2000).is_err());
    assert!(parse_hex_meters_or(Some("big"), 2000).is_err());
}

// ---- parameter_cd ---------------------------------------------------------

#[test]
fn parameter_cd_optional() {
    assert_eq!(parse_parameter_cd_opt(None), None);
    assert_eq!(parse_parameter_cd_opt(Some("")), None);
    assert_eq!(parse_parameter_cd_opt(Some("  ")), None);
    assert_eq!(parse_parameter_cd_opt(Some("00010")), Some("00010".to_string()));
    assert_eq!(parse_parameter_cd_opt(Some(" 00060 ")), Some("00060".to_string()));
}
