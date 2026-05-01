-- Bootstrap database + dedicated user for the KlinikAsistan backend.
-- Runs once on first container start (when the data volume is empty).

CREATE DATABASE IF NOT EXISTS klinikasistan
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'klinik'@'%' IDENTIFIED BY 'klinik';
GRANT ALL PRIVILEGES ON klinikasistan.* TO 'klinik'@'%';
FLUSH PRIVILEGES;
