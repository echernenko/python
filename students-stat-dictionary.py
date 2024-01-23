students = {
               'John' : { 'Math' : 48, 'English' : 60, 'Science' : 95},
               'Richard' : { 'Math' : 75,'English' : 68,'Science' : 89},
               'Charles' : { 'Math' : 45,'English' : 66,'Science' : 87}
           }
students_stat = {}
max_average = -1
max_student = None
for student,stat in students.items():
  total = sum(stat.values())
  average = total // len(stat)
  if average > max_average:
    max_average = average
    max_student = student
  students_stat[student] = {}
  students_stat[student]['Total'] = total
  students_stat[student]['Average'] = average
print(students_stat)
print('Top student of the class:', max_student)
print('Top student\'s score:', max_average)
