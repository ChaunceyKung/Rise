from urllib.parse import urlsplit

def loopback_endpoint(value):
    if type(value) is not str:return False
    try:
        u=urlsplit(value)
        return (u.scheme=='http' and u.hostname=='127.0.0.1' and u.port is not None and 1024<=u.port<=65535 and
                value==f'http://127.0.0.1:{u.port}' and not u.username and not u.password)
    except ValueError:return False
