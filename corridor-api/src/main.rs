//! corridor-api — axum + sqlx HTTP service for the Sturgeon Run platform.
//!
//! Serves species, occurrences, stations, readings and the derived hex-bin
//! "corridor" density layer out of PostGIS. GeoJSON is assembled in Postgres
//! for efficiency and streamed back as a raw JSON string.

use std::net::SocketAddr;

use axum::{
    extract::{Query, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Row};
use std::collections::HashMap;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use corridor_api::params::{
    parse_date_opt, parse_hex_meters_or, parse_limit, parse_parameter_cd_opt, parse_species_id_opt,
    parse_species_id_or,
};

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    hex_meters_default: i32,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let database_url = std::env::var("DATABASE_URL")
        .expect("DATABASE_URL must be set (postgres://user:pass@host:port/db)");
    let bind = std::env::var("CORRIDOR_API_BIND").unwrap_or_else(|_| "0.0.0.0:8080".to_string());
    let hex_meters_default: i32 = std::env::var("CORRIDOR_HEX_METERS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(2000);

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("failed to connect to database");

    let state = AppState {
        pool,
        hex_meters_default,
    };

    let app = Router::new()
        .route("/healthz", get(healthz))
        .route("/api/species", get(species))
        .route("/api/occurrences", get(occurrences))
        .route("/api/stations", get(stations))
        .route("/api/readings/latest", get(readings_latest))
        .route("/api/corridor", get(corridor))
        .route("/api/corridor/summary", get(corridor_summary))
        .route("/api/corridor/derive", post(corridor_derive))
        .route("/api/quality-report", get(quality_report))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let addr: SocketAddr = bind.parse().expect("invalid CORRIDOR_API_BIND");
    tracing::info!("corridor-api listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind");
    axum::serve(listener, app).await.expect("server error");
}

// ---------------------------------------------------------------------------
// Response helpers
// ---------------------------------------------------------------------------

/// Wrap a raw JSON string (already serialized by Postgres) in a 200 response
/// with the correct content-type.
fn json_string(body: String) -> Response {
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "application/json")],
        body,
    )
        .into_response()
}

/// Build a `{"error": msg}` response with the given status code.
fn json_error(status: StatusCode, msg: impl Into<String>) -> Response {
    let body = serde_json::json!({ "error": msg.into() }).to_string();
    (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
}

/// Log a DB error and return a 500.
fn db_error(context: &str, err: sqlx::Error) -> Response {
    tracing::error!("db error during {context}: {err}");
    json_error(StatusCode::INTERNAL_SERVER_ERROR, "internal database error")
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

async fn healthz(State(state): State<AppState>) -> Response {
    match sqlx::query("SELECT 1").execute(&state.pool).await {
        Ok(_) => (
            StatusCode::OK,
            [(header::CONTENT_TYPE, "application/json")],
            serde_json::json!({"status":"ok","db":"ok"}).to_string(),
        )
            .into_response(),
        Err(e) => {
            tracing::error!("healthz db check failed: {e}");
            (
                StatusCode::SERVICE_UNAVAILABLE,
                [(header::CONTENT_TYPE, "application/json")],
                serde_json::json!({"status":"error","db":"down"}).to_string(),
            )
                .into_response()
        }
    }
}

async fn species(State(state): State<AppState>) -> Response {
    let sql = r#"
        SELECT COALESCE(
            json_agg(json_build_object(
                'id', id,
                'gbif_taxon_key', gbif_taxon_key,
                'scientific_name', scientific_name,
                'common_name', common_name
            ) ORDER BY id),
            '[]'::json
        )::text AS body
        FROM species
    "#;
    match sqlx::query(sql).fetch_one(&state.pool).await {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("species", e),
    }
}

async fn occurrences(
    State(state): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let from = match parse_date_opt("from", q.get("from").map(String::as_str)) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };
    let to = match parse_date_opt("to", q.get("to").map(String::as_str)) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };
    let species_id = match parse_species_id_opt(q.get("species_id").map(String::as_str)) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };
    let limit = match parse_limit(q.get("limit").map(String::as_str)) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };

    let sql = r#"
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(f.feature), '[]'::json)
        )::text AS body
        FROM (
            SELECT json_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(geom)::json,
                'properties', json_build_object(
                    'id', id,
                    'gbif_id', gbif_id,
                    'event_date', event_date,
                    'year', year,
                    'basis_of_record', basis_of_record,
                    'coordinate_uncertainty', coordinate_uncertainty,
                    'dataset_key', dataset_key
                )
            ) AS feature
            FROM occurrences
            WHERE ($1::date IS NULL OR event_date >= $1::date)
              AND ($2::date IS NULL OR event_date <= $2::date)
              AND ($3::int  IS NULL OR species_id = $3::int)
            ORDER BY id
            LIMIT $4::bigint
        ) f
    "#;
    match sqlx::query(sql)
        .bind(from)
        .bind(to)
        .bind(species_id)
        .bind(limit)
        .fetch_one(&state.pool)
        .await
    {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("occurrences", e),
    }
}

async fn stations(State(state): State<AppState>) -> Response {
    let sql = r#"
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(json_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(geom)::json,
                'properties', json_build_object(
                    'id', id,
                    'site_no', site_no,
                    'name', name,
                    'agency_cd', agency_cd,
                    'site_type_cd', site_type_cd
                )
            )), '[]'::json)
        )::text AS body
        FROM stations
    "#;
    match sqlx::query(sql).fetch_one(&state.pool).await {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("stations", e),
    }
}

async fn readings_latest(
    State(state): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let parameter_cd = parse_parameter_cd_opt(q.get("parameter_cd").map(String::as_str));

    let sql = r#"
        SELECT COALESCE(json_agg(json_build_object(
            'station_id', r.station_id,
            'site_no', r.site_no,
            'name', r.name,
            'parameter_cd', r.parameter_cd,
            'parameter_name', r.parameter_name,
            'value', r.value,
            'unit', r.unit,
            'measured_at', r.measured_at
        )), '[]'::json)::text AS body
        FROM (
            SELECT DISTINCT ON (rd.station_id, rd.parameter_cd)
                rd.station_id,
                s.site_no,
                s.name,
                rd.parameter_cd,
                rd.parameter_name,
                rd.value,
                rd.unit,
                rd.measured_at
            FROM readings rd
            JOIN stations s ON s.id = rd.station_id
            WHERE ($1::text IS NULL OR rd.parameter_cd = $1::text)
            ORDER BY rd.station_id, rd.parameter_cd, rd.measured_at DESC
        ) r
    "#;
    match sqlx::query(sql)
        .bind(parameter_cd)
        .fetch_one(&state.pool)
        .await
    {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("readings_latest", e),
    }
}

async fn corridor(
    State(state): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let species_id = match parse_species_id_or(q.get("species_id").map(String::as_str), 1) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };

    let sql = r#"
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(json_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(geom)::json,
                'properties', json_build_object(
                    'id', id,
                    'occurrence_count', occurrence_count,
                    'hex_meters', hex_meters
                )
            )), '[]'::json)
        )::text AS body
        FROM corridor_cells
        WHERE species_id = $1::int
    "#;
    match sqlx::query(sql)
        .bind(species_id)
        .fetch_one(&state.pool)
        .await
    {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("corridor", e),
    }
}

async fn corridor_summary(
    State(state): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let species_id = match parse_species_id_or(q.get("species_id").map(String::as_str), 1) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };

    let sql = r#"
        WITH c AS (
            SELECT * FROM corridor_cells WHERE species_id = $1::int
        )
        SELECT json_build_object(
            'species_id', $1::int,
            'cell_count', (SELECT COUNT(*) FROM c),
            'occurrence_count', (SELECT COALESCE(SUM(occurrence_count), 0) FROM c),
            'hex_meters', (SELECT MAX(hex_meters) FROM c),
            'max_cell_count', (SELECT COALESCE(MAX(occurrence_count), 0) FROM c),
            'computed_at', (SELECT MAX(computed_at) FROM c),
            'bbox', (
                SELECT CASE WHEN COUNT(*) = 0 THEN NULL ELSE json_build_array(
                    ST_XMin(ST_Extent(geom)),
                    ST_YMin(ST_Extent(geom)),
                    ST_XMax(ST_Extent(geom)),
                    ST_YMax(ST_Extent(geom))
                ) END
                FROM c
            )
        )::text AS body
    "#;
    match sqlx::query(sql)
        .bind(species_id)
        .fetch_one(&state.pool)
        .await
    {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("corridor_summary", e),
    }
}

async fn quality_report(State(state): State<AppState>) -> Response {
    // Latest run = the run_id whose MAX(run_at) is greatest. A single ingest
    // run inserts one row per source sharing a run_id. Reconstruct the JSON
    // shape of data/quality-report.json from those rows.
    let sql = r#"
        WITH latest AS (
            SELECT run_id
            FROM data_quality_reports
            GROUP BY run_id
            ORDER BY MAX(run_at) DESC
            LIMIT 1
        ),
        rows AS (
            SELECT d.*
            FROM data_quality_reports d
            JOIN latest l ON l.run_id = d.run_id
        )
        SELECT CASE
            WHEN NOT EXISTS (SELECT 1 FROM rows) THEN
                json_build_object(
                    'run_id', NULL,
                    'generated_at', NULL,
                    'snapshot_mode', false,
                    'sources', '[]'::json
                )
            ELSE
                json_build_object(
                    'run_id', (SELECT run_id FROM rows LIMIT 1),
                    'generated_at', (SELECT MAX(run_at) FROM rows),
                    'snapshot_mode', (SELECT bool_or(snapshot_mode) FROM rows),
                    'sources', (
                        SELECT json_agg(json_build_object(
                            'source', source,
                            'snapshot_mode', snapshot_mode,
                            'records_fetched', records_fetched,
                            'records_kept', records_kept,
                            'records_dropped', records_dropped,
                            'drop_reasons', drop_reasons,
                            'notes', notes,
                            'run_at', run_at
                        ) ORDER BY source)
                        FROM rows
                    )
                )
            END::text AS body
    "#;
    match sqlx::query(sql).fetch_one(&state.pool).await {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("quality_report", e),
    }
}

async fn corridor_derive(
    State(state): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let species_id = match parse_species_id_or(q.get("species_id").map(String::as_str), 1) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };
    let hex_meters = match parse_hex_meters_or(
        q.get("hex_meters").map(String::as_str),
        state.hex_meters_default,
    ) {
        Ok(v) => v,
        Err(m) => return json_error(StatusCode::BAD_REQUEST, m),
    };

    // Idempotent replace inside a transaction: wipe existing cells, then rebuild
    // the hex-bin density surface from occurrences using ST_HexagonGrid.
    let mut tx = match state.pool.begin().await {
        Ok(t) => t,
        Err(e) => return db_error("corridor_derive begin", e),
    };

    if let Err(e) = sqlx::query("DELETE FROM corridor_cells WHERE species_id = $1::int")
        .bind(species_id)
        .execute(&mut *tx)
        .await
    {
        return db_error("corridor_derive delete", e);
    }

    // Occurrences are transformed to EPSG:32618 (UTM 18N, metric) so the hex
    // edge length is expressed in meters; cells are stored back in EPSG:4326.
    let insert_sql = r#"
        INSERT INTO corridor_cells (species_id, occurrence_count, hex_meters, geom, computed_at)
        SELECT $1::int, hex.cnt, $2::int, ST_Transform(hex.geom, 4326), now()
        FROM (
            SELECT h.geom AS geom, COUNT(o.g) AS cnt
            FROM ST_HexagonGrid(
                    $2::float,
                    (SELECT ST_SetSRID(ST_Extent(ST_Transform(geom, 32618))::geometry, 32618)
                     FROM occurrences WHERE species_id = $1::int)
                 ) AS h
            JOIN (
                SELECT ST_Transform(geom, 32618) AS g
                FROM occurrences WHERE species_id = $1::int
            ) o ON ST_Intersects(h.geom, o.g)
            GROUP BY h.geom
            HAVING COUNT(o.g) > 0
        ) hex
    "#;
    if let Err(e) = sqlx::query(insert_sql)
        .bind(species_id)
        .bind(hex_meters as f64)
        .execute(&mut *tx)
        .await
    {
        return db_error("corridor_derive insert", e);
    }

    if let Err(e) = tx.commit().await {
        return db_error("corridor_derive commit", e);
    }

    // Report the resulting counts.
    let counts_sql = r#"
        SELECT json_build_object(
            'species_id', $1::int,
            'cell_count', (SELECT COUNT(*) FROM corridor_cells WHERE species_id = $1::int),
            'occurrence_count', (SELECT COUNT(*) FROM occurrences WHERE species_id = $1::int),
            'hex_meters', $2::int
        )::text AS body
    "#;
    match sqlx::query(counts_sql)
        .bind(species_id)
        .bind(hex_meters)
        .fetch_one(&state.pool)
        .await
    {
        Ok(row) => json_string(row.get::<String, _>("body")),
        Err(e) => db_error("corridor_derive counts", e),
    }
}
