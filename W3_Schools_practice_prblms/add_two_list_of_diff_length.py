# Python program to add two given lists of different lengths, start from left. Go to the editor
# Original lists:
# [2, 4, 7, 0, 5, 8]
# [3, 3, -1, 7]
# Add said two lists from left:
# [5, 7, 6, 7, 5, 8]
# Original lists:
# [1, 2, 3, 4, 5, 6]
# [2, 4, -3]
# Add said two lists from left:
# [3, 6, 0, 4, 5, 6]

lst1=[2, 4, 7, 0, 5, 8]
lst2=[3, 3, -1, 7]
# lst1=[1, 2, 3, 4, 5, 6]
# lst2=[2, 4, -3]

l1_len=len(lst1)
l2_len=len(lst2)

if l1_len>l2_len:
    for ele in range(0,l2_len):
        lst1[ele]=lst1[ele]+lst2[ele]
    new=lst1
else:
    for ele in range(0,l1_len):
        lst2[ele]=lst1[ele]+lst2[ele]
    new=lst2
print(new)

