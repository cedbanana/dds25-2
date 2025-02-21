import time


def hosttotup(host):
    host, port = host.split(":")
    return (host, int(port))


def wait_for_ignite():
    time.sleep(5)
