"""A scientific calculator with safe expression evaluation.

Supports full math expressions with operator precedence, parentheses,
scientific functions, and constants. Examples:

    sin(pi/2) + cos(0)
    sqrt(2) ** 2
    log(100, 10)
    2^10            (^ is treated as exponentiation)
    factorial(5)
    3 + 4 * 2 / (1 - 5)
"""

import ast
import math
import operator

# --- Allowed names -----------------------------------------------------------

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
}

FUNCTIONS = {
    # trigonometric
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
    # angle conversion
    "degrees": math.degrees, "radians": math.radians,
    # powers / logs
    "sqrt": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "exp": math.exp, "log": math.log, "log2": math.log2, "log10": math.log10,
    "pow": math.pow,
    # rounding / misc
    "abs": abs, "ceil": math.ceil, "floor": math.floor, "round": round,
    "trunc": math.trunc, "fabs": math.fabs,
    "factorial": math.factorial, "gcd": math.gcd,
    "hypot": math.hypot, "copysign": math.copysign,
    "max": max, "min": min,
}

# --- Operators ---------------------------------------------------------------

BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitXor: operator.pow,  # treat ^ as exponentiation (calculator convention)
}

UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval(node):
    """Recursively evaluate a restricted AST node."""
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator")
        return op(_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported unary operator")
        return op(_eval(node.operand))
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise ValueError(f"Unknown name: {node.id!r}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise ValueError("Unknown or unsupported function call")
        args = [_eval(a) for a in node.args]
        return FUNCTIONS[node.func.id](*args)
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def evaluate(expr):
    """Safely evaluate a mathematical expression string."""
    tree = ast.parse(expr, mode="eval")
    return _eval(tree)


HELP = """Scientific Calculator
---------------------
Type an expression and press Enter. Examples:
    sin(pi/2) + cos(0)
    sqrt(2) ** 2          2^10           log(100, 10)
    factorial(5)          3 + 4*2/(1-5)  degrees(pi)

Functions: sin cos tan asin acos atan atan2 sinh cosh tanh
           sqrt cbrt exp log log2 log10 pow hypot
           ceil floor round trunc abs factorial gcd degrees radians ...
Constants: pi  e  tau  inf  nan
Commands : 'help' to show this, 'q' / 'quit' / 'exit' to leave.
"""


def main():
    print(HELP)
    while True:
        try:
            expr = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not expr:
            continue
        low = expr.lower()
        if low in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        if low in ("help", "?"):
            print(HELP)
            continue
        try:
            print(f"= {evaluate(expr)}")
        except ZeroDivisionError:
            print("Error: division by zero")
        except (ValueError, SyntaxError) as e:
            print(f"Error: {e}")
        except Exception as e:  # math domain errors, arg errors, etc.
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
