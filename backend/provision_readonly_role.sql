-- CLEAN PROJECT HEADER
-- ไฟล์: provision_readonly_role.sql
-- หน้าที่: ให้บริการ API, Agent, RAG หรือ GIS ตามชื่อโมดูล
-- Input: คำขอ API, config และ canonical spatial data
-- Output: ผลลัพธ์ JSON/GeoJSON หรือหลักฐานระบบ
-- Dependency สำคัญ: project_paths.py และโมดูล backend ที่เกี่ยวข้อง
-- สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
-- Template only: replace placeholders locally; never commit a real password.
-- Run with an authorized administrator after choosing a dedicated login name.
CREATE ROLE <APP_READONLY_ROLE> LOGIN PASSWORD '<STRONG_LOCAL_SECRET>';
GRANT CONNECT ON DATABASE <DATABASE_NAME> TO <APP_READONLY_ROLE>;
GRANT USAGE ON SCHEMA geoai_a7t TO <APP_READONLY_ROLE>;
GRANT SELECT ON geoai_a7t.landcover_polygons TO <APP_READONLY_ROLE>;
GRANT SELECT ON geoai_a7t.dataset_metadata TO <APP_READONLY_ROLE>;
ALTER ROLE <APP_READONLY_ROLE> SET default_transaction_read_only = on;
REVOKE CREATE ON SCHEMA public FROM <APP_READONLY_ROLE>;
