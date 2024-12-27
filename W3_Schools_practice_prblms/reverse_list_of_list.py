lst=[['orange', 'red'], ['green', 'blue'], ['white', 'black', 'pink']]
lst=[[1, 2, 3, 4], [0, 2, 4, 5], [2, 3, 4, 2, 4]]


#EXPECTED [['white', 'black', 'pink'], ['green', 'blue'], ['orange', 'red']]
#[[1, 2, 3, 4], [0, 2, 4, 5], [2, 3, 4, 2, 4]]

print(lst[::-1])
#OUTPUT [['white', 'black', 'pink'], ['green', 'blue'], ['orange', 'red']]
# [[2, 3, 4, 2, 4], [0, 2, 4, 5], [1, 2, 3, 4]]


