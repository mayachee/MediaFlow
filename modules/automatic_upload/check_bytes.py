enc = b'v20\x1ce8\xc3Y'
print('First 3 bytes:', enc[:3])
print('First 3 bytes hex:', enc[:3].hex())
print('Is v10:', enc[:3] == b'v10')
print('Is v20:', enc[:3] == b'v20')
for i, b in enumerate(enc[:5]):
    char = chr(b) if 32 <= b < 127 else '?'
    print(f'Byte {i}: {b} = 0x{b:02x} = {char}')
