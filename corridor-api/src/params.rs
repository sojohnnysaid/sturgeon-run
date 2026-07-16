//! Pure query-parameter parsing functions.
//!
//! These are deliberately DB-free so they can be unit tested without a live
//! database. Each returns a `Result<_, String>` where the `Err` string becomes
//! the body of a `400 {"error": ...}` response.

use chrono::NaiveDate;

/// Default number of occurrence features returned when `limit` is omitted.
pub const DEFAULT_LIMIT: i64 = 5000;
/// Hard cap on the number of occurrence features returned.
pub const MAX_LIMIT: i64 = 50000;

/// Parse an optional `YYYY-MM-DD` date string.
///
/// - `None` / empty string  -> `Ok(None)` (filter not applied)
/// - valid date             -> `Ok(Some(date))`
/// - anything else          -> `Err(msg)`
pub fn parse_date_opt(field: &str, raw: Option<&str>) -> Result<Option<NaiveDate>, String> {
    match raw {
        None => Ok(None),
        Some(s) if s.trim().is_empty() => Ok(None),
        Some(s) => NaiveDate::parse_from_str(s.trim(), "%Y-%m-%d")
            .map(Some)
            .map_err(|_| format!("invalid {field} date '{s}', expected YYYY-MM-DD")),
    }
}

/// Parse an optional integer `species_id`.
pub fn parse_species_id_opt(raw: Option<&str>) -> Result<Option<i32>, String> {
    match raw {
        None => Ok(None),
        Some(s) if s.trim().is_empty() => Ok(None),
        Some(s) => s
            .trim()
            .parse::<i32>()
            .map(Some)
            .map_err(|_| format!("invalid species_id '{s}', expected an integer")),
    }
}

/// Parse a `species_id` that has a default when omitted (used by corridor
/// endpoints where the default species is 1).
pub fn parse_species_id_or(raw: Option<&str>, default: i32) -> Result<i32, String> {
    Ok(parse_species_id_opt(raw)?.unwrap_or(default))
}

/// Parse an optional `limit`, applying the default and cap.
///
/// - omitted / empty -> `DEFAULT_LIMIT`
/// - valid > MAX     -> capped to `MAX_LIMIT`
/// - valid <= 0      -> `Err`
/// - non-integer     -> `Err`
pub fn parse_limit(raw: Option<&str>) -> Result<i64, String> {
    match raw {
        None => Ok(DEFAULT_LIMIT),
        Some(s) if s.trim().is_empty() => Ok(DEFAULT_LIMIT),
        Some(s) => {
            let n = s
                .trim()
                .parse::<i64>()
                .map_err(|_| format!("invalid limit '{s}', expected an integer"))?;
            if n <= 0 {
                return Err(format!("invalid limit '{s}', must be positive"));
            }
            Ok(n.min(MAX_LIMIT))
        }
    }
}

/// Parse an optional hex-grid edge length in meters (for corridor derivation).
pub fn parse_hex_meters_or(raw: Option<&str>, default: i32) -> Result<i32, String> {
    match raw {
        None => Ok(default),
        Some(s) if s.trim().is_empty() => Ok(default),
        Some(s) => {
            let n = s
                .trim()
                .parse::<i32>()
                .map_err(|_| format!("invalid hex_meters '{s}', expected an integer"))?;
            if n <= 0 {
                return Err(format!("invalid hex_meters '{s}', must be positive"));
            }
            Ok(n)
        }
    }
}

/// Parse an optional `parameter_cd` filter. Empty is treated as "no filter".
pub fn parse_parameter_cd_opt(raw: Option<&str>) -> Option<String> {
    match raw {
        None => None,
        Some(s) if s.trim().is_empty() => None,
        Some(s) => Some(s.trim().to_string()),
    }
}
