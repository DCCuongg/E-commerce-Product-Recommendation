-- Mật khẩu mặc định băm bằng bcrypt cho 'Password123!': $2b$12$e8Y...
INSERT INTO
    users (
        id,
        username,
        email,
        hashed_password,
        role
    )
VALUES (
        'U_ADMIN_01',
        'admin',
        'admin@ecommerce.local',
        '$2b$12$KIXeWq1i8jYpB34r82K0n.LwK9f9B0i6GhzUqW2pM1iXj4A1p/ZKi',
        'admin'
    ),
    (
        'U_TEST_01',
        'cuongduong',
        'cuong@ecommerce.local',
        '$2b$12$KIXeWq1i8jYpB34r82K0n.LwK9f9B0i6GhzUqW2pM1iXj4A1p/ZKi',
        'customer'
    ),
    (
        'U_TEST_02',
        'testuser',
        'test@ecommerce.local',
        '$2b$12$KIXeWq1i8jYpB34r82K0n.LwK9f9B0i6GhzUqW2pM1iXj4A1p/ZKi',
        'customer'
    ) ON CONFLICT (id) DO NOTHING;