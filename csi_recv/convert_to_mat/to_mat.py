import pandas as pd
import numpy as np
import json
import scipy.io as sio

def convert_to_wimans_format(input_csv, output_filename):
    # 1. Load the CSV
    df = pd.read_csv(input_csv)
    
    csi_list = []
    
    for index, row in df.iterrows():
        # 2. Parse the JSON string in the 'data' column
        raw_data = json.loads(row['data'])
        
        # 3. Convert interleaved Real/Imag to Complex
        # Espressif usually sends: [Imag, Real, Imag, Real...]
        imag = np.array(raw_data[::2])
        real = np.array(raw_data[1::2])
        
        complex_data = real + 1j * imag
        csi_list.append(complex_data)

    # 4. Create the Matrix: (Packets, Subcarriers)
    csi_matrix = np.array(csi_list)

    # 5. Save as .mat (Most compatible with WiMANS/MATLAB tools)
    # WiMANS often looks for a dict key 'csi'
    sio.savemat(f"{output_filename}.mat", {'csi': csi_matrix})
    print(f"Successfully converted to {output_filename}.mat")
    print(f"Shape: {csi_matrix.shape}")

convert_to_wimans_format('csi_output/csi_data.csv', 'wimans_ready_data')