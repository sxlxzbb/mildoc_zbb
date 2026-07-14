
def write_file(content, file_path):
    with open(file_path, mode='a', encoding='utf-8') as filename:
        filename.write(content)
        filename.write('\n')
        filename.write('---------------------------------------------')
        filename.write('\n')

