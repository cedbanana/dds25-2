import time
import random


def hosttotup(host):
    host, port = host.split(":")
    return (host, int(port))


def wait_for_ignite():
    time.sleep(6)


def randsleep():
    time.sleep(random.randint(1, 50) / 100)
