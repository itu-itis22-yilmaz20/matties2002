x=67
guess=int(input("make a guess(the number is between 0 and 100):"))
if guess==x:
          print("You win")
else          :
    print("You have lost")


Num=int(input('write an integer number:'))
i=0;j=0
while i<Num:
    i=i+1
    j=j+1
print('The sum of numbers from 1 to',Num,'equals:',j)     
Num1=int(input('Enter lower range:'))
Num2=int(input('Enter upper range:'))
print("Prime numbers between",Num1,"and",Num2,"are:")
k=Num1
while k<=Num2:
    Flag=True
   #prime numbers are greater than 1
    if k>1:
        m=2
        while m<k:
            if(k%m)==0:
                Flag=False
                break
            m=m+1
    if Flag:print(k)
    k=k+1


while i<10:
    if(i==5):
        break
    print(i)
    i=i+1
x=10
while x:
    x=x-1
    if x%2!=0:continue
#Odd?--skip printing
    print(x,end='')
i=0
while i<90:
    i=i+1
else:
    print(i)
    print('Iteration is completed')


n=100
def factorial(n):
    if n<=1:
        return 1
    f=1
    for i in range(n,1,-1):
        f*=i
        return f


