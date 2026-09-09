import sqlite3
import sys

def tamper(piece_id, seq_index, new_note):
    conn = sqlite3.connect('craftproof.db')
    c = conn.cursor()
    
    # Update note without updating hash or signature
    c.execute("UPDATE custody_records SET note = ? WHERE piece_id = ? AND seq_index = ?", (new_note, piece_id, seq_index))
    conn.commit()
    conn.close()
    print(f"Successfully tampered record {seq_index} of piece {piece_id} with new note: '{new_note}'")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python tamper_demo.py <piece_id> <seq_index> <new_note>")
        sys.exit(1)
        
    tamper(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
