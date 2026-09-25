CREATE TABLE visitors_v2 (
 id TEXT PRIMARY KEY,
 email TEXT,
 name TEXT NOT NULL,
 industry TEXT,
 contact_consent INTEGER NOT NULL CHECK(contact_consent IN (0,1)),
 notice_version TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 access_expires INTEGER NOT NULL,
 CHECK(contact_consent = 0 OR email IS NOT NULL)
);
INSERT INTO visitors_v2 SELECT * FROM visitors;
DROP TABLE visitors;
ALTER TABLE visitors_v2 RENAME TO visitors;
CREATE INDEX visitors_created_at ON visitors(created_at);
