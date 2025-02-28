# -*- coding: utf-8 -*-
"""
Created on Fri Feb 28 14:51:27 2025

@author: ejones
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import geopandas as gpd

def browse_file(entry_widget, filetypes, dropdown):
    filepath = filedialog.askopenfilename(filetypes=filetypes)
    if filepath:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, filepath)
        
        # If it's a shapefile, update the dropdown with field names
        if filepath.endswith(".shp"):
            try:
                gdf = gpd.read_file(filepath)
                field_names = list(gdf.columns)
                dropdown['menu'].delete(0, 'end')
                for field in field_names:
                    dropdown['menu'].add_command(label=field, command=tk._setit(dropdown.variable, field))
                dropdown.variable.set(field_names[0] if field_names else "")
            except Exception as e:
                messagebox.showerror("Error", f"Could not read shapefile: {e}")

def update_model(inp_path, valves_path, hydrants_path, valve_id, hydrant_id):
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Model Update", f"EPANET INP File: {inp_path}\nValves Shapefile: {valves_path}\nValve ID Field: {valve_id}\nHydrants Shapefile: {hydrants_path}\nHydrant ID Field: {hydrant_id}\n\nThe model is updating...")

def submit_action(root, inp_entry, valves_entry, hydrants_entry, valve_dropdown, hydrant_dropdown):
    inp_path = inp_entry.get()
    valves_path = valves_entry.get()
    hydrants_path = hydrants_entry.get()
    valve_id = valve_dropdown.variable.get()
    hydrant_id = hydrant_dropdown.variable.get()
    root.destroy()
    update_model(inp_path, valves_path, hydrants_path, valve_id, hydrant_id)

def create_ui():
    root = tk.Tk()
    root.title("EPANET & Shapefile Selector")
    root.geometry("600x300")
    
    tk.Label(root, text="EPANET INP File:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    inp_entry = tk.Entry(root, width=50)
    inp_entry.grid(row=0, column=1, padx=10, pady=5)
    tk.Button(root, text="Browse", command=lambda: browse_file(inp_entry, [("EPANET INP Files", "*.inp")], None)).grid(row=0, column=2, padx=5, pady=5)
    
    tk.Label(root, text="Valves Shapefile:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
    valves_entry = tk.Entry(root, width=50)
    valves_entry.grid(row=1, column=1, padx=10, pady=5)
    
    valve_dropdown = tk.OptionMenu(root, tk.StringVar(), "")
    valve_dropdown.variable = valve_dropdown['menu'].var = tk.StringVar()
    valve_dropdown.grid(row=2, column=1, padx=10, pady=5)
    
    tk.Button(root, text="Browse", command=lambda: browse_file(valves_entry, [("Shapefiles", "*.shp")], valve_dropdown)).grid(row=1, column=2, padx=5, pady=5)
    
    tk.Label(root, text="Valve ID Field:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
    
    tk.Label(root, text="Hydrants Shapefile:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
    hydrants_entry = tk.Entry(root, width=50)
    hydrants_entry.grid(row=3, column=1, padx=10, pady=5)
    
    hydrant_dropdown = tk.OptionMenu(root, tk.StringVar(), "")
    hydrant_dropdown.variable = hydrant_dropdown['menu'].var = tk.StringVar()
    hydrant_dropdown.grid(row=4, column=1, padx=10, pady=5)
    
    tk.Button(root, text="Browse", command=lambda: browse_file(hydrants_entry, [("Shapefiles", "*.shp")], hydrant_dropdown)).grid(row=3, column=2, padx=5, pady=5)
    
    tk.Label(root, text="Hydrant ID Field:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
    
    tk.Button(root, text="Submit", command=lambda: submit_action(root, inp_entry, valves_entry, hydrants_entry, valve_dropdown, hydrant_dropdown)).grid(row=5, column=1, pady=20)
    
    root.mainloop()

if __name__ == "__main__":
    create_ui()
