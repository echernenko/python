# simplest approach
dt1 = (17, 3, 1998)
dt2 = (17, 4, 2011)
diff = (dt2[2] - dt1[2]) * 365 + (dt2[1] - dt1[1]) * 30 +  (dt2[0] - dt1[0])

print('Difference in days =', diff)


# with the library
from datetime import date

d0 = date(1998, 3, 17)
d1 = date(2011, 4, 17)
delta = d1 - d0
print('Difference in days =', delta.days)


# manual, detailed
dt1 = (17, 3, 1998)
dt2 = (17, 4, 2011)

d1, m1, y1 = dt1[0], dt1[1], dt1[2]
d2, m2, y2 = dt2[0], dt2[1], dt2[2]

days1 = [31, 0, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
days2 = [31, 0, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

ndays1 = (y1 - 1) * 365
ldays1 = ((y1 - 1) // 4) - ((y1 - 1) // 100) + ((y1 - 1) // 400)
tdays1 = ndays1 + ldays1

if((y1 % 4 == 0 and y1 % 100 != 0) or (y1 % 400 == 0)) :
    days1[1] = 29
else :
    days1[1] = 28

s1 = sum(days1[0:m1 - 1])
tdays1 += s1

ndays2 = (y2 - 1) * 365
ldays2 = ((y2 -1) // 4) - ((y2 - 1) // 100) + ((y2 - 1) // 400)
tdays2 = ndays2 + ldays2

if((y2 % 4 == 0 and y2 % 100 != 0) or (y2 % 400 == 0)) :
    days2[1] = 29
else :
    days2[1] = 28

s2 = sum(days2[0:m2 - 1])
tdays2 += s2

diff = tdays2 - tdays1
print('Difference in days =', diff)

