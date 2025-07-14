import bcrypt
import os

def hash_password(password):
    # Generiere einen Salzwert. bcrypt handhabt das automatisch.
    # Es wird dringend empfohlen, bcrypt das Salzen überlassen.
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed_password.decode('utf-8')

if __name__ == "__main__":
    password = input("Geben Sie das Passwort ein, das gehasht werden soll: ")
    hashed = hash_password(password)
    print(f"\nIhr gehashtes Passwort: {hashed}")
    print("\nSpeichern Sie diesen Hash (beginnt mit $2b$...) in Ihrer Umgebungsvariable oder Konfigurationsdatei.")