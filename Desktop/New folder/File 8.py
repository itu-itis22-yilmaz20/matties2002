width, price_width = 40, 10
item_width = width - price_width
header_format = '%-*s%*s'
format = '%-*s%*.2f'
print ('=' * width)
print (header_format % (item_width, 'Item', price_width, 'Price (TL)') )
print ('-' * width)
print (format % (item_width, 'Apples (1 kg.)', price_width, 5.0) )
print (format % (item_width, 'Pears (2 kg)', price_width, 12.0) )
print (format % (item_width, 'Potato (3 kg)', price_width, 6.0) )
print (format % (item_width, 'Dried Apricots (100 gr)', price_width, 8) )
print (format % (item_width, 'Tomato (1 kg)', price_width, 4.0) )
print ('=' * width)
"{name} is {age} years old".format(name="Berke",age=21)

