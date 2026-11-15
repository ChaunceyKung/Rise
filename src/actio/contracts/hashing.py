import hashlib

def sha(raw):return hashlib.sha256(raw.encode()).hexdigest()
