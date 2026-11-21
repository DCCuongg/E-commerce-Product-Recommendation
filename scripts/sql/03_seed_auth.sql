-- Kích hoạt pgcrypto để sinh mã băm bcrypt chuẩn ($2a$12$...) cho 'Password123!'
CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO
    users (
        id,
        username,
        email,
        hashed_password,
        role,
        is_disabled
    )
VALUES (
        'U_ADMIN_01',
        'admin',
        'admin@ecommerce.local',
        crypt (
            'Password123!',
            gen_salt ('bf', 12)
        ),
        'admin',
        FALSE
    ),
    (
        'U_TEST_01',
        'cuongduong',
        'cuong@ecommerce.local',
        crypt (
            'Password123!',
            gen_salt ('bf', 12)
        ),
        'customer',
        FALSE
    ),
    (
        'U_TEST_02',
        'testuser',
        'test@ecommerce.local',
        crypt (
            'Password123!',
            gen_salt ('bf', 12)
        ),
        'customer',
        FALSE
    ),
    (
        'U_CUST_03',
        'minhanh_music',
        'minhanh@ecommerce.local',
        crypt (
            'Password123!',
            gen_salt ('bf', 12)
        ),
        'customer',
        FALSE
    ),
    (
        'U_CUST_04',
        'hoangnam_studio',
        'hoangnam@ecommerce.local',
        crypt (
            'Password123!',
            gen_salt ('bf', 12)
        ),
        'customer',
        FALSE
    ) ON CONFLICT (id) DO NOTHING;