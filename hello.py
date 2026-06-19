"""A simple Python program."""


def greet(name):
    """Return a friendly greeting."""
    return f"Hello, {name}!"


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


def main():
    print(greet("World"))
    print(f"2 + 3 = {add(2, 3)}")

    # Print squares of the first 5 numbers
    for i in range(1, 6):
        print(f"{i} squared is {i ** 2}")


if __name__ == "__main__":
    main()
