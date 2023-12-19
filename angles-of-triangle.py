import math

def angles_of_triangle(): 
  a, b, c = 3, 4, 5

  angleA = (math.acos((b * b + c * c - a * a ) / ( 2 * b * c )) * 180) / 3.14
  print("Angle A:", angleA)

  angleB = (math.acos((a * a + c * c - b * b ) / ( 2 * a * c )) * 180) / 3.14
  print("Angle B:", angleB)

  angleC = (math.acos((a * a + b * b - c * c ) / ( 2 * a * b )) * 180) / 3.14
  print("Angle C:", angleC)

angles_of_triangle()
