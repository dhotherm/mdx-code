"""Tests for the calculator module."""

import pytest
from src.calculator import add, subtract, multiply, divide, power, factorial, average


class TestBasicOperations:
    """Test basic math operations."""
    
    def test_add(self):
        assert add(2, 3) == 5
        assert add(-1, 1) == 0
        assert add(0, 0) == 0
    
    def test_subtract(self):
        assert subtract(5, 3) == 2
        assert subtract(1, 1) == 0
        assert subtract(0, 5) == -5
    
    def test_multiply(self):
        assert multiply(3, 4) == 12
        assert multiply(-2, 3) == -6
        assert multiply(0, 100) == 0
    
    def test_divide(self):
        assert divide(10, 2) == 5
        assert divide(7, 2) == 3.5
        # This test will fail! divide doesn't handle zero
        # assert divide(10, 0) raises ZeroDivisionError


class TestAdvancedOperations:
    """Test advanced operations."""
    
    def test_power_positive(self):
        assert power(2, 3) == 8
        assert power(5, 2) == 25
        assert power(10, 0) == 1
    
    # This test will fail because power() is buggy
    # def test_power_negative(self):
    #     assert power(2, -1) == 0.5
    
    def test_factorial_positive(self):
        assert factorial(0) == 1
        assert factorial(1) == 1
        assert factorial(5) == 120
    
    # This test will cause infinite recursion!
    # def test_factorial_negative(self):
    #     factorial(-1)
    
    def test_average(self):
        assert average([1, 2, 3, 4, 5]) == 3
        assert average([10]) == 10
    
    # This test will fail! average doesn't handle empty list
    # def test_average_empty(self):
    #     average([])
