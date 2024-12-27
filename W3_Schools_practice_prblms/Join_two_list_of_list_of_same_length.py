#  Python program to join two given list of lists of same length, element wise. Go to the editor
# Original lists:
# [[10, 20], [30, 40], [50, 60], [30, 20, 80]]
# [[61], [12, 14, 15], [12, 13, 19, 20], [12]]
# Join the said two lists element wise:
# [[10, 20, 61], [30, 40, 12, 14, 15], [50, 60, 12, 13, 19, 20], [30, 20, 80, 12]]
# Original lists:
# [['a', 'b'], ['b', 'c', 'd'], ['e', 'f']]
# [['p', 'q'], ['p', 's', 't'], ['u', 'v', 'w']]
# Join the said two lists element wise:
# [['a', 'b', 'p', 'q'], ['b', 'c', 'd', 'p', 's', 't'], ['e', 'f', 'u', 'v', 'w']]

lst1= [[10, 20], [30, 40], [50, 60], [30, 20, 80]]
lst2= [[61], [12, 14, 15], [12, 13, 19, 20], [12]]
new=[]
for l1,l2 in zip(lst1,lst2):
    new.append(l1+l2)
print(new)

#**************************************************************
d=[ele1+ele2 for ele1,ele2 in zip(lst1,lst2)]
print(d)

