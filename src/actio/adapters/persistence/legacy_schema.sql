PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('epoch','0');
CREATE TABLE IF NOT EXISTS agent(id TEXT PRIMARY KEY,spec_hash TEXT NOT NULL,spec TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS run(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,input_hash TEXT NOT NULL,input TEXT NOT NULL,
 epoch INTEGER NOT NULL,state TEXT NOT NULL,task TEXT NOT NULL,trajectory TEXT NOT NULL,reason TEXT,stop_requested INTEGER DEFAULT 0,
 owner_pid INTEGER NOT NULL,owner_birth TEXT NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lease(singleton INTEGER PRIMARY KEY CHECK(singleton=1),run TEXT UNIQUE REFERENCES run(id),epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS worker(id TEXT PRIMARY KEY,run TEXT REFERENCES run(id),epoch INTEGER,root TEXT UNIQUE,job TEXT UNIQUE,pid INTEGER,state TEXT,report TEXT);
CREATE TABLE IF NOT EXISTS stream(id TEXT PRIMARY KEY,run TEXT REFERENCES run(id),worker TEXT REFERENCES worker(id),agent TEXT REFERENCES agent(id),native_id TEXT,
 creation TEXT UNIQUE,native_store TEXT,generation TEXT DEFAULT 'session.v3.jsonl',path TEXT,header TEXT,cursor INTEGER DEFAULT -1,
 consumed_bytes INTEGER DEFAULT 0,integrity TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS operation(id TEXT PRIMARY KEY,run TEXT REFERENCES run(id),stream TEXT REFERENCES stream(id),epoch INTEGER,
 input_hash TEXT,state TEXT,receipt TEXT,terminal TEXT,barrier TEXT,answer TEXT,reason TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,run TEXT,op TEXT,kind TEXT,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS occurrence(stream TEXT REFERENCES stream(id),seq INTEGER,raw_hash TEXT,raw TEXT,PRIMARY KEY(stream,seq));
CREATE TABLE IF NOT EXISTS conflict(stream TEXT,seq INTEGER,old_hash TEXT,new_hash TEXT,raw TEXT,PRIMARY KEY(stream,seq,new_hash));
CREATE TABLE IF NOT EXISTS projection(stream TEXT,seq INTEGER,slot TEXT,mapper TEXT,value TEXT,PRIMARY KEY(stream,seq,slot,mapper),
 FOREIGN KEY(stream,seq) REFERENCES occurrence(stream,seq));
CREATE TABLE IF NOT EXISTS consumer(name TEXT PRIMARY KEY,mapper TEXT,slots TEXT);
INSERT OR IGNORE INTO consumer VALUES('episodic','v1','["assistant.final"]');
CREATE TABLE IF NOT EXISTS memory_head(namespace TEXT PRIMARY KEY,revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS memory(id TEXT,revision INTEGER,namespace TEXT,content TEXT,stream TEXT,seq INTEGER,slot TEXT,policy TEXT,time INTEGER,
 PRIMARY KEY(id,revision),UNIQUE(namespace,revision),FOREIGN KEY(stream,seq) REFERENCES occurrence(stream,seq));
CREATE TABLE IF NOT EXISTS effect(consumer TEXT,stream TEXT,seq INTEGER,slot TEXT,memory_id TEXT,revision INTEGER,namespace TEXT,
 PRIMARY KEY(consumer,stream,seq,slot));
CREATE TABLE IF NOT EXISTS retrieval(id TEXT PRIMARY KEY,namespace TEXT,as_of INTEGER,selection TEXT,context TEXT,policy TEXT);
CREATE TABLE IF NOT EXISTS world(run TEXT,step INTEGER,agent TEXT,intent TEXT,resolved TEXT,stream TEXT,seq INTEGER,
 PRIMARY KEY(run,step),FOREIGN KEY(stream,seq) REFERENCES occurrence(stream,seq));
CREATE TABLE IF NOT EXISTS domain_receipt(op TEXT PRIMARY KEY REFERENCES operation(id),outcome TEXT,stream TEXT,seq INTEGER,body TEXT);
