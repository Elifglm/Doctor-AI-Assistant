-- OpenEMR icin database + user olusturma
-- phpMyAdmin SQL sekmesinden veya `mysql -u root -p < setup_db.sql` ile calistirilir

-- 1) Database olustur (utf8mb4)
CREATE DATABASE IF NOT EXISTS `openemr`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

-- 2) User olustur (sifre: openemr)
CREATE USER IF NOT EXISTS 'openemr'@'localhost' IDENTIFIED BY 'openemr';

-- 3) openemr DB'sinde tum yetkileri ver
GRANT ALL PRIVILEGES ON `openemr`.* TO 'openemr'@'localhost';

-- 4) Yetkileri yukle
FLUSH PRIVILEGES;

-- 5) Dogrulama (sonuc gormek icin)
SELECT User, Host FROM mysql.user WHERE User = 'openemr';
SHOW GRANTS FOR 'openemr'@'localhost';
