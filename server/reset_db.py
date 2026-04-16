from bootstrap import reset_database


if __name__ == '__main__':
    # After reset, load fixtures with: python server/import_csv.py
    reset_database()
    print('Database reset complete.')
