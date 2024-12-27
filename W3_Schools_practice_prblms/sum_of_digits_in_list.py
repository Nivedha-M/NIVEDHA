lst=[10, 20, 4, 5, 'b', 70, 'a']

sum_digits=0
for ele in lst:
    st_digit=str(ele)
    print(st_digit,type(st_digit))
    if st_digit.isdigit():
        if len(st_digit)>1:
            sum_digits+=int(st_digit[0])+int(st_digit[1])
        else:
            sum_digits+=int(st_digit)
print(sum_digits)

#EFFICIENT WAY=================================================================================================
print("***************ONE LINE CODE*******************")


print(sum(int(digits) for ele in lst for digits in str(ele) if digits.isdigit()))
