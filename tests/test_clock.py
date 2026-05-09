import threading
from utils import LamportClock


def print_result(test_name, passed):
    """
    Print standardized PASS/FAIL result.
    """

    if passed:
        print(f"[PASS] {test_name}")
    else:
        print(f"[FAIL] {test_name}")


def test_initial_value():
    """
    Test that initial clock value is 0.
    """

    clock = LamportClock()

    passed = (clock.value() == 0)

    print_result("test_initial_value", passed)


def test_tick():
    """
    Test tick() increments correctly.
    """

    clock = LamportClock()

    first = clock.tick()
    second = clock.tick()

    passed = (first == 1 and second == 2)

    print_result("test_tick", passed)


def test_send():
    """
    Test send() increments correctly.
    """

    clock = LamportClock()

    value = clock.send()

    passed = (value == 1)

    print_result("test_send", passed)


def test_receive_higher():
    """
    receive(10) on local clock 3 -> 11
    """

    clock = LamportClock()

    clock.tick()
    clock.tick()
    clock.tick()

    value = clock.receive(10)

    passed = (value == 11)

    print_result("test_receive_higher", passed)


def test_receive_lower():
    """
    receive(1) on local clock 5 -> 6
    """

    clock = LamportClock()

    for _ in range(5):
        clock.tick()

    value = clock.receive(1)

    passed = (value == 6)

    print_result("test_receive_lower", passed)


def test_receive_equal():
    """
    receive(5) on local clock 5 -> 6
    """

    clock = LamportClock()

    for _ in range(5):
        clock.tick()

    value = clock.receive(5)

    passed = (value == 6)

    print_result("test_receive_equal", passed)


def test_thread_safety():
    """
    100 threads each increment the clock once.
    Final value should be exactly 100.
    """

    clock = LamportClock()

    threads = []

    def worker():
        clock.tick()

    # Create 100 threads
    for _ in range(100):
        t = threading.Thread(target=worker)
        threads.append(t)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for all threads to finish
    for t in threads:
        t.join()

    passed = (clock.value() == 100)

    print_result("test_thread_safety", passed)


if __name__ == "__main__":

    print("Running LamportClock tests...\n")

    test_initial_value()
    test_tick()
    test_send()
    test_receive_higher()
    test_receive_lower()
    test_receive_equal()
    test_thread_safety()
