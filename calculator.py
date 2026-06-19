"""A simple command-line calculator."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


OPERATIONS = {
    "+": add,
    "-": subtract,
    "*": multiply,
    "/": divide,
}


def calculate(a, op, b):
    """Apply the operator `op` to numbers `a` and `b`."""
    if op not in OPERATIONS:
        raise ValueError(f"Unknown operator: {op!r}")
    return OPERATIONS[op](a, b)


def main():
    print("Simple Calculator (type 'q' to quit)")
    print("Example: 3 + 4")
    while True:
        expr = input("> ").strip()
        if expr.lower() in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        try:
            a, op, b = expr.split()
            result = calculate(float(a), op, float(b))
            print(f"= {result}")
        except ZeroDivisionError as e:
            print(f"Error: {e}")
        except (ValueError, TypeError):
            print("Invalid input. Use format: number operator number (e.g. 3 + 4)")


if __name__ == "__main__":
    main()
