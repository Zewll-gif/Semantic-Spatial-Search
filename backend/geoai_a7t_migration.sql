-- CLEAN PROJECT HEADER
-- ไฟล์: geoai_a7t_migration.sql
-- หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
-- Input: คำขอ API, config และ canonical spatial data
-- Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
-- Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
-- สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
-- A7-T GeoAI Backend Foundation V1
-- Run with an authorized PostGIS connection; credentials are intentionally not included.
CREATE SCHEMA IF NOT EXISTS geoai_a7t;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS geoai_a7t.landcover_polygons (
  id BIGSERIAL PRIMARY KEY,
  polygon_id INTEGER UNIQUE NOT NULL,
  class_id SMALLINT NOT NULL CHECK (class_id BETWEEN 1 AND 7),
  class_code VARCHAR(4) NOT NULL,
  class_name VARCHAR(80) NOT NULL,
  area_m2 DOUBLE PRECISION NOT NULL,
  area_ha DOUBLE PRECISION NOT NULL,
  area_km2 DOUBLE PRECISION NOT NULL,
  area_rai DOUBLE PRECISION NOT NULL,
  perimeter_m DOUBLE PRECISION NOT NULL,
  source_model VARCHAR(20) NOT NULL,
  source_raster VARCHAR(128) NOT NULL,
  model_version VARCHAR(64) NOT NULL,
  geom geometry(MultiPolygon,32647) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS landcover_polygons_geom_gist ON geoai_a7t.landcover_polygons USING GIST (geom);
CREATE INDEX IF NOT EXISTS landcover_polygons_class_id_idx ON geoai_a7t.landcover_polygons (class_id);
CREATE INDEX IF NOT EXISTS landcover_polygons_class_code_idx ON geoai_a7t.landcover_polygons (class_code);
CREATE TABLE IF NOT EXISTS geoai_a7t.dataset_metadata (
  dataset_key VARCHAR(64) PRIMARY KEY,
  dataset_name VARCHAR(160) NOT NULL,
  dataset_type VARCHAR(64) NOT NULL,
  source TEXT,
  crs VARCHAR(32),
  resolution DOUBLE PRECISION,
  acquisition_date DATE,
  model_version VARCHAR(64),
  description TEXT,
  limitations TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
-- Vector load (execute after schema creation, with GDAL/ogr2ogr):
-- ogr2ogr -f PostgreSQL "PG:dbname=<db> host=<host> user=<user>" D:\499_4\FINAL_ANALYSIS\A7_T_VECTOR_BACKEND\vector_clean\A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg -nln geoai_a7t.landcover_polygons -nlt PROMOTE_TO_MULTI -a_srs EPSG:32647
