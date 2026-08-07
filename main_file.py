import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta
from getpass import getpass

# ========== НАСТРОЙКИ ==========
ENGINE = 'stock'
MARKET = 'shares'
DATE_FROM = '2000-01-01'
DATE_TO = '2026-01-01'          
LIMIT = 100                      
SLEEP = 0.3                      
OUTPUT_CSV = 'moex_history_daily_2000_2026.csv'
TEMP_PREFIX = 'temp_moex_history'
# ================================

session = requests.Session()
print("Введите логин и пароль от подписки Московской биржи:")
username = input("Логин: ")
password = getpass("Пароль: ")
session.auth = (username, password)
session.headers.update({'Accept': 'application/json', 'User-Agent': 'ISS-Client/1.0'})

def date_range(start_date, end_date):
    cur = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    while cur < end:
        yield cur.strftime('%Y-%m-%d')
        cur += timedelta(days=1)

def fetch_day_data(date, columns=None):
    all_rows = []
    start = 0
    total = None
    first_page = True

    while True:
        url = (f"https://iss.moex.com/iss/history/engines/{ENGINE}/markets/{MARKET}/securities.json"
               f"?date={date}&start={start}&limit={LIMIT}")
        # Добавляем iss.meta=on только на первом запросе для получения колонок
        if first_page and columns is None:
            url += "&iss.meta=on"

        for attempt in range(3):
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                print(f"  {date}: ошибка запроса (попытка {attempt+1}): {e}")
                time.sleep(2)
        else:
            print(f"  {date}: не удалось получить данные, пропускаем.")
            return [], columns

        if 'history' not in data or not data['history'].get('data'):
            # Нет данных за этот день
            return [], columns

        # Если первый запрос и колонки неизвестны, извлекаем их
        if first_page and columns is None:
            cols_info = data['history']['columns']
            if cols_info and isinstance(cols_info[0], dict):
                columns = [col['name'] for col in cols_info]
            else:
                columns = cols_info
            first_page = False

        rows = data['history']['data']
        all_rows.extend(rows)

        # Пагинация через cursor
        cursor_data = data.get('history.cursor', {}).get('data')
        if cursor_data and len(cursor_data) > 0:
            cur_info = cursor_data[0]
            if len(cur_info) >= 3:
                pagesize = cur_info[1]
                total = cur_info[2]
                start += pagesize
                if start >= total:
                    break
            else:
                break
        else:
            break

        time.sleep(SLEEP)

    return all_rows, columns

def save_yearly_data(year, data, columns):
    """Сохраняет данные за год во временный файл."""
    if not data:
        return
    filename = f"{TEMP_PREFIX}_{year}.csv"
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"Сохранён год {year}: {len(df)} записей в {filename}")

def load_yearly_data(year):
    """Загружает данные за год, если файл существует."""
    filename = f"{TEMP_PREFIX}_{year}.csv"
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        print(f"Загружен год {year}: {len(df)} записей")
        return df.values.tolist()
    return None

def main():
    # Определяем список годов для контроля
    start_year = int(DATE_FROM[:4])
    end_year = int(DATE_TO[:4])
    years = range(start_year, end_year + 1)

    # Загружаем уже собранные данные по годам
    all_data = []
    columns = None

    # Попытка загрузить колонки из первого существующего файла
    for year in years:
        df_cols = load_yearly_data(year)
        if df_cols is not None and columns is None:
            # Восстанавливаем колонки из первого загруженного файла
            temp_df = pd.read_csv(f"{TEMP_PREFIX}_{year}.csv")
            columns = temp_df.columns.tolist()
            all_data.extend(temp_df.values.tolist())
            print(f"Колонки определены из файла {year}.csv")
            break
        elif df_cols is not None:
            all_data.extend(df_cols)

    # Если колонки не найдены, получим их при первом успешном запросе
    # Начинаем перебор дней
    current_year = None
    yearly_data = []

    print("Начинаем подневной сбор данных...")
    for date_str in date_range(DATE_FROM, DATE_TO):
        year = date_str[:4]
        # Если перешли на новый год, сохраняем предыдущий и начинаем новый список
        if current_year is not None and year != current_year:
            if yearly_data:
                save_yearly_data(current_year, yearly_data, columns)
                all_data.extend(yearly_data)
                yearly_data = []
            current_year = year
        elif current_year is None:
            current_year = year
              
        print(f"Обрабатываем {date_str}")
        day_rows, columns = fetch_day_data(date_str, columns)
        if day_rows:
            print(f"  получено {len(day_rows)} записей")
            yearly_data.extend(day_rows)
        else:
            print(f"  данных нет")
        time.sleep(SLEEP)

    # Сохраняем последний год
    if yearly_data:
        save_yearly_data(current_year, yearly_data, columns)
        all_data.extend(yearly_data)

    if not all_data:
        print("Нет данных для сохранения.")
        return

    # Объединяем все данные в один DataFrame и сохраняем
    df = pd.DataFrame(all_data, columns=columns)
    print(f"Всего собрано записей: {len(df)}")
    df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✅ Финальные данные сохранены в {OUTPUT_CSV}")

    # Дополнительно сохраняем в Parquet
    try:
        df.to_parquet(OUTPUT_CSV.replace('.csv', '.parquet'), index=False)
        print(f"✅ Также сохранено в Parquet")
    except ImportError:
        pass

if __name__ == '__main__':
    main()
