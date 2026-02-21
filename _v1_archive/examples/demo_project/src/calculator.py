"""
Calculator Module

A simple calculator with some intentional bugs for demo purposes.
Let's see if MDx Code can find and fix them!
"""


def add(a, b):
    """Add two numbers."""
    return a + b


def subtract(a, b):
    """Subtract b from a."""
    return a - b


def multiply(a, b):
    """Multiply two numbers."""
    return a * b


def divide(a, b):
    """Divide a by b.
    
    BUG: No zero division check!
    """
    return a / b


def power(base, exponent):
    """Calculate base raised to exponent.
    
    BUG: This implementation is wrong for negative exponents!
    """
    result = 1
    for _ in range(exponent):
        result *= base
    return result


def factorial(n):
    """Calculate factorial of n.
    
    BUG: No input validation! Negative numbers will cause infinite recursion.
    """
    if n == 0:
        return 1
    return n * factorial(n - 1)


def average(numbers):
    """Calculate average of a list of numbers.
    
    BUG: Empty list will cause ZeroDivisionError!
    """
    return sum(numbers) / len(numbers)


# This is intentionally bad code for the security scanner to find
password = "admin123"  # Hardcoded password - security issue!
api_key = "sk-1234567890abcdef1234567890abcdef"  # Hardcoded API key!
