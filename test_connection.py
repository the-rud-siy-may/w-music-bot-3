import uiautomator2 as u2

try:
    d = u2.connect()

    print("Connected successfully!")
    print(d.info)

except Exception as e:
    print("Connection failed:")
    print(e)