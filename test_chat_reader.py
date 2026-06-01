import uiautomator2 as u2

d = u2.connect()

messages = d.xpath('//*[@resource-id="com.wakie.android:id/text"]').all()
users = d.xpath('//*[@resource-id="com.wakie.android:id/name"]').all()

print("\n--- USERS ---")
for u in users:
    try:
        print(u.text)
    except:
        pass

print("\n--- MESSAGES ---")
for m in messages:
    try:
        print(m.text)
    except:
        pass