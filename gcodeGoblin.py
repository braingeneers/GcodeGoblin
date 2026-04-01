import sys
import re

from bambuuzle.bambu_file import transform

def remove_extrusion(line):
    if line.startswith('G1 ') or line.startswith('G2 ') or line.startswith('G3 '):
        return re.sub(r'\sE[0-9.-]+', '', line)
    return line

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
    disable_extrusion = False
    lineno = 0
    for line in lines:
        lineno += 1
        line = line.strip()  # Remove leading/trailing whitespace
        if not cutting:
            if disable_extrusion:
                output.append(remove_extrusion(line))
            else:
                output.append(line)
        # Check for buffer commands with insensitivity
        if detect_command('; START_COPY:', line):
            # Extract the buffer name
            buffer_name = line.split(':')[1].strip()
            print(f"Start copy {buffer_name}")
            buffers[buffer_name] = []  # Initialize the buffer
            output.append(f'; starting to copy into buffer {buffer_name}')
            current_buffer = buffer_name
        elif detect_command('; STOP_COPY:', line):
            output.append(f'; stopping copy into buffer {current_buffer}')
            buffer_name = line.split(':')[1].strip()
            print(f"Stop copy {buffer_name}")
            current_buffer = None  # Stop copying lines
        elif detect_command('; STOP_EXTRUDE:', line):
            print("Disabling extrusion")
            disable_extrusion=True
        elif detect_command('; START_EXTRUDE:', line):
            print("Enabling extrusion")
            disable_extrusion=False
        elif current_buffer:
            # Add line to the current buffer
            buffers[current_buffer].append(line)
        elif detect_command('; PASTE:', line):
            # Extract the buffer name to paste
            buffer_name = line.split(':')[1].strip()
            print(f"paste buffer {buffer_name}")
            if buffer_name in buffers:
                output.append(f'; pasting from buffer {buffer_name} into output:')
                # Output all lines stored in the buffer
                for buffered_line in buffers[buffer_name]:
                    output.append(buffered_line)
                output.append("; END OF PASTE BUFFER")
        elif detect_command('; REMOVE_EXTRUSION:', line):
            buffer_name = line.split(':')[1].strip()
            if buffer_name in buffers:
                print(f'Removing extrusion activity from Buffer {buffer_name}')
                newBuf = []
                for buffered_line in buffers[buffer_name]:
                    newBuf.append(remove_extrusion(buffered_line))
                buffers[buffer_name] = newBuf
        elif detect_command('; PRINT_BUFFER', line):
            buffer_name = line.split(':')[1].strip()
            if buffer_name in buffers:
                print(f'; pasting from buffer {buffer_name} into output:')
                # Output all lines stored in the buffer
                for buffered_line in buffers[buffer_name]:
                    print(buffered_line)
                print(f"; END OF PASTE BUFFER {buffer_name}")
        elif detect_command('; START_CUT', line):
            output.append("; CUT START")
            print("Cut start")
            cutting = True
        elif detect_command('; STOP_CUT', line):
            output.append("; CUT STOPPED")
            print("Cut stop")
            cutting = False
            

    
    return output

def process_zip_file(zip_filename):
    """Process the .gcode inside a .3mf file using bambuuzle."""
    fixed_zip_filename = zip_filename.replace('.3mf', '.fixed.3mf')

    def goblin_transform(gcode):
        lines = gcode.splitlines()
        processed = process_lines(lines)
        return '\n'.join(processed)

    transform(zip_filename, fixed_zip_filename, goblin_transform)

def process_gcode(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()
        new_content = process_lines(lines)
        fixed_filename = filename.replace(".gcode", ".fixed.gcode")
        with open(fixed_filename, 'w') as out_file:
            for line in new_content:
                out_file.write(line)
                out_file.write("\n")

def print_message():
    print("Usage: python script.py <filename>")
    print("       <filename> can be a .3mf file or a gcode file")
    sys.exit(1)

def main():
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


if __name__ == "__main__":
    main()
