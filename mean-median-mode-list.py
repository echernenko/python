lst = [10, 20, 30, 40, 30, 60, 70, 30, 80, 30]
lst_len = len(lst)
mean = sum(lst) / lst_len
# sorting the list to calculate median
lst.sort()
median = None
# if the list has an odd number of elements, the median is the middle element
# if the list has an even number of elements, the median is the average of the two middle elements
if (lst_len % 2 != 0) :
    # dividing and roundig to lower integer
    median = lst[lst_len // 2]
else :
    half_index = lst_len // 2;
    median = (lst[half_index] + lst[half_index - 1]) / 2
# getting mode
# lst is now
# lst = [10, 20, 30, 30, 30, 30, 40, 60, 70, 80]
# initial values
curr_num = lst[0]
mode = curr_num
sequence_num = 1
max_sequence_num = 1;
for i in range(1, lst_len) :
    num = lst[i]
    if (curr_num == num) :
        sequence_num += 1
        if (sequence_num > max_sequence_num) :
            max_sequence_num = sequence_num
            mode = num
    else :
        sequence_num = 1
        curr_num = num

print('List =', lst)
print('Mean =', mean)
print('Median =', median)
print('Mode =', mode)

