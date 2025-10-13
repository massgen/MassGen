import math

def factorial(n: int) -> int:
    """Compute the factorial of a non-negative integer n using math.factorial.

    This function leverages the highly optimized built-in math.factorial
    for efficient computation, while also providing explicit input validation.

    Parameters:
        n (int): Non-negative integer to compute the factorial of.

    Returns:
        int: The factorial of n (n!).

    Raises:
        TypeError: If n is not an integer.
        ValueError: If n < 0.
    """
    if not isinstance(n, int):
        raise TypeError("n must be a non-negative integer")
    if n < 0:
        raise ValueError("n must be a non-negative integer")

    return math.factorial(n)

# Example Usage
print(factorial(5))  # Output: 120