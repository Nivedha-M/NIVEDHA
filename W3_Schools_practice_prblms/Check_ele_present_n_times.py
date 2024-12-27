# Python program to check if a given element occurs at least n times in a list. Go to the editor
# Original list:
# [0, 1, 3, 5, 0, 3, 4, 5, 0, 8, 0, 3, 6, 0, 3, 1, 1, 0]
# Check if 3 occurs at least 4 times in a list:
# True
# Check if 0 occurs at least 5 times in a list:
# True
# Check if 8 occurs at least 3 times in a list:
# False

lst=[0, 1, 3, 5, 0, 3, 4, 5, 0, 8, 0, 3, 6, 0, 3, 1, 1, 0]
def n_occurance(lst,ele,n):
    occurance=lst.count(ele)
    print(occurance)
    if occurance>=n:
        return True
    else:
        return False
print(n_occurance(lst,3,4))
print(n_occurance(lst,0,5))
print(n_occurance(lst,8,3))



