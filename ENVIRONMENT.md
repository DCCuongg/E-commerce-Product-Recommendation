Dưới đây là hướng dẫn tạo môi trường ảo (Virtual Environment) và file quản lý thư viện (`requirements.txt`) cho Python theo chuẩn thực hành phổ biến nhất:

---

### Bước 1: Mở Terminal / Command Prompt tại thư mục dự án

Điều hướng đến thư mục chứa mã nguồn của bạn:

```bash
cd "đường/dẫn/tới/thư_mục_dự_án"

```

---

### Bước 2: Tạo môi trường ảo

Sử dụng module tích hợp sẵn `venv` của Python (tên môi trường thường đặt là `.venv` hoặc `venv`):

```bash
# Trên Windows / macOS / Linux
python -m venv .venv

```

*(Nếu trên Linux/macOS bạn dùng lệnh `python3`, hãy thay bằng `python3 -m venv .venv`)*.

---

### Bước 3: Kích hoạt môi trường ảo

* **Trên Windows:**
* **Command Prompt (cmd):**
```cmd
.venv\Scripts\activate.bat

```


* **PowerShell:**
```powershell
.venv\Scripts\Activate.ps1

```


*(Nếu PowerShell báo lỗi bảo mật chính sách script, mở PowerShell quyền Admin và chạy: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, sau đó kích hoạt lại).*


* **Trên macOS / Linux:**
```bash
source .venv/bin/activate

```



> Khi kích hoạt thành công, bạn sẽ thấy tiền tố `(.venv)` xuất hiện ở đầu dòng lệnh trong terminal.

---

### Bước 4: Cài đặt các thư viện cần thiết

Khi môi trường ảo đã kích hoạt, hãy cài đặt các gói cần cho dự án bằng `pip`:

```bash
# Ví dụ cài đặt các thư viện cho Azure và dotenv:
pip install azure-storage-blob azure-cosmos python-dotenv

```

---

### Bước 5: Tạo file quản lý thư viện (`requirements.txt`)

Sau khi cài đặt xong, xuất danh sách toàn bộ thư viện cùng phiên bản chính xác ra file:

```bash
pip freeze > requirements.txt

```

Nội dung file `requirements.txt` tạo ra sẽ có dạng:

```text
azure-core==1.30.1
azure-cosmos==4.6.0
azure-storage-blob==12.19.1
python-dotenv==1.0.1
...

```

---

### Các thao tác thường dùng tiếp theo

* **Khi người khác (hoặc trên máy khác) muốn cài lại toàn bộ thư viện:**
```bash
pip install -r requirements.txt

```


* **Thoát khỏi môi trường ảo:**
```bash
deactivate

```


* **Lưu ý Git:** Thêm thư mục môi trường ảo vào file `.gitignore` để không đẩy cả môi trường ảo lên GitHub:
```text
.venv/
venv/
__pycache__/
.env

```