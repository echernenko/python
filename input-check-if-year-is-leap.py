year = input('Please enter the year to check if it\'s a leap one:  ')
year = int(year)
leap = False;
if (year % 4 == 0):
    leap = True;
    if (year % 100 == 0):
        leap = False;
        if (year % 400 == 0):
            leap = True;
print (str(year) + ' is ' + ('' if leap else 'NOT ') + 'a Leap Year') 
    
