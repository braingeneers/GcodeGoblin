import sys
import zipfile
import hashlib
import os

def extract_gcode_content(zip_filename):
    """Extracts lines from the first .gcode file found in the Metadata/ directory."""
    content = None
    original_file_name = None
    with zipfile.ZipFile(zip_filename, 'r') as zip_file:
        for file_info in zip_file.infolist():
            if file_info.filename.startswith('Metadata/') and file_info.filename.endswith('.gcode'):
                with zip_file.open(file_info.filename) as gcode_file:
                    content = gcode_file.read().decode().splitlines()
                original_file_name = file_info.filename
                break
    return content, original_file_name

def detect_command(command, line):
    """Checks for command insensitivity."""
    line = line.replace(" ", "")
    command = command.replace(" ", "")
    return line.strip().lower().startswith(command.lower())

def process_lines(lines):
    """Processes lines from the .gcode file."""
    buffers = {}
    current_buffer = None
    output = []
    cutting = False
    lineno = 0
    for line in lines:
        lineno += 1
        line = line.strip()  # Remove leading/trailing whitespace
        if not cutting:
            output.append(line)  # Collect output for testing

        # Check for buffer commands with insensitivity
        if detect_command('; START_COPY:', line):
            # Extract the buffer name
            buffer_name = line.split(':')[1].strip()
            print("Start copy {buffer_name}")
            buffers[buffer_name] = []  # Initialize the buffer
            output.append(f'; starting to copy into buffer {buffer_name}')
            current_buffer = buffer_name
        elif detect_command('; STOP_COPY:', line):
            output.append(f'; stopping copy into buffer {current_buffer}')
            print("Stop copy {buffer_name}")
            current_buffer = None  # Stop copying lines
        elif current_buffer:
            # Add line to the current buffer
            buffers[current_buffer].append(line)
        elif detect_command('; PASTE:', line):
            # Extract the buffer name to paste
            buffer_name = line.split(':')[1].strip()
            print("paste buffer {current_buffer}")
            if buffer_name in buffers:
                output.append(f'; pasting from buffer {buffer_name} into output:')
                # Output all lines stored in the buffer
                for buffered_line in buffers[buffer_name]:
                    output.append(buffered_line)
                output.append("; END OF PASTE BUFFER")
        elif detect_command('; START_CUT', line):
            output.append("; CUT START")
            print("Cut start")
            cutting = True
        elif detect_command('; STOP_CUT', line):
            output.append("; CUT STOPPED")
            print("Cut stop")
            cutting = False
            

    
    return output

def calculate_md5(file_content):
    """Calculates the MD5 checksum of the given file content."""
    md5 = hashlib.md5()
    md5.update(file_content.encode('utf-8'))
    return md5.hexdigest()

def process_zip_file(zip_filename):
    """Main function to process the .gcode file in the zip."""
    lines, original_file_name = extract_gcode_content(zip_filename)
    if lines is not None and original_file_name is not None:
        new_content = process_lines(lines)
        md5_checksum = calculate_md5('\n'.join(new_content))
        
        # Create a new zip file with .fixed.3mf extension
        fixed_zip_filename = zip_filename.replace('.3mf', '.fixed.3mf')
        
        with zipfile.ZipFile(zip_filename, 'r') as original_zip:
            with zipfile.ZipFile(fixed_zip_filename, 'w') as fixed_zip:
                for file_info in original_zip.infolist():
                    # Write all files except the original .gcode and .md5
                    if file_info.filename != original_file_name and not file_info.filename.endswith('.md5'):
                        fixed_zip.writestr(file_info, original_zip.read(file_info.filename))
                
                # Write the processed .gcode file
                fixed_zip.writestr(original_file_name, '\n'.join(new_content).encode('utf-8'))
                
                # Write the new .md5 file
                md5_file_name = original_file_name + '.md5'
                fixed_zip.writestr(md5_file_name, md5_checksum)

def process_gcode(filename):
    with open('file.txt', 'r') as file:
        lines = file.readlines()
        new_content = process_lines(lines)
        fixed_filename = filename.replace(".gcode", ".fixed.gcode")
        with open(fixed_filename, 'w') as out_file:
            for line in new_content:
                out_file.write(line)

def print_message():
    print("Usage: python script.py <filename>")
    print("       <filename> can be a .3mf file or a gcode file")
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_message()
    
    filename = sys.argv[1]
    if filename.endswith(".3mf"):
        process_zip_file(filename)
    elif filename.endswith(".gcode"):
        process_gcode(filename)
    else:
        print("ERROR: filename is neither .3mf nor .gcode")
        print_message()


