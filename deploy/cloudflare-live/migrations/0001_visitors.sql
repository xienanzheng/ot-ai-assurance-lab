CREATE TABLE visitors (
 id TEXT PRIMARY KEY,
 email TEXT NOT NULL,
 name TEXT NOT NULL,
 industry TEXT NOT NULL,
 contact_consent INTEGER NOT NULL CHECK(contact_consent IN (0,1)),
 notice_version TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 access_expires INTEGER NOT NULL
);
CREATE INDEX visitors_created_at ON visitors(created_at);
