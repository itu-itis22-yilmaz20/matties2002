#Read numbers
Num1=int(input("Enter lower range:"))for
Num2=int(input("Enter upper range:"))
print("Prime numbers between",Num1,"and",Num2,"are:")
k=Num1
while k<=Num2:
    Flag=True
    #prime numbers are grater than 1
    if k>1:
        m=2
        while m<k:
            if(k%m)==0:
                Flag=False
                break
            m=m+1
    if Flag:print(k)
    k=k+1
print("I will ask you a question\n""you can make 2 predictions!")
print("What is the ratio between Earth and Sun ?")
i=1
while(i<=5):
    print(i,'.prediction')
    number=int(input("Ratio:"))
    if(number=="1000000"):
        print("Congratulations!")
        break
    i=i+1
else:#when loop is completed
    print("You couldn't find the answer,it is 1000000")
              
for num in [1,2,3]:
    print(num)

    
