# -*- coding: utf-8 -*-
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import config

import os
from PIL import Image
import colorgram
from io import BytesIO
import sqlite3

API_TOKEN = config.TOKEN
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    hi = '👋 Hello, ' + message.from_user.first_name + ', send me image and I create palette!'
    await message.answer(hi)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def process_photo(message: types.Message, state: FSMContext):
    await bot.send_chat_action(message.chat.id, 'upload_photo')
    fileID = message.photo[-1].file_id
    file_info = await bot.get_file(fileID)

    downloaded_file = (await bot.download_file(file_info.file_path)).read()
    my_path = str(fileID) + '.jpg'
    with open(my_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    colors = clrs(colorgram.extract(my_path, 6))
    os.remove(os.path.join(os.path.abspath(os.path.dirname(__file__)), my_path))

    for color in colors:
        img = image_to_byte_array(Image.new('RGB', (320, 125), color))
        if colors[-1] == color:
            markup = InlineKeyboardMarkup()
            markup.row_width = 2
            markup.add(InlineKeyboardButton('Save palette', callback_data='save'))
            await message.answer_photo(img, caption=f'`{color}`', parse_mode='MARKDOWN', reply_markup=markup)
        else:
            await message.answer_photo(img, caption=f'`{color}`', parse_mode='MARKDOWN')

    async with state.proxy() as data:
        data['palette'] = colors

@dp.callback_query_handler(lambda c: c.data == 'save')
async def save_palette_callback(callback_query: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if 'palette' in data.keys():
            conn = sqlite3.connect("users.db")
            cursor = conn.cursor()
            cursor.execute('INSERT INTO palettes VALUES(?, ?)', (callback_query.message.chat.id, ', '.join(data['palette'])))
            conn.commit()
            conn.close()
            await callback_query.message.delete_reply_markup()
            await callback_query.message.answer('Saved!')
        else:
            await bot.answer_callback_query(callback_query.id, 'I’m sorry, I can’t save it.')

@dp.message_handler(commands=['palettes'])
async def send_palettes(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM palettes WHERE cid = {message.chat.id}')
    palettes = cursor.fetchall()
    if len(palettes) == 0:
        await message.answer('You don’t have any palettes.')
    elif len(palettes) == 1:
        markup = color_markup(palettes[0][1].split(', '))
        await message.answer('Your palette', reply_markup=markup)
    else:
        palettes = [p[1].split(', ') for p in palettes]
        async with state.proxy() as data:
            data['palettes'] = palettes
            data['palindex'] = 0
        markup = color_markup(palettes[0])
        markup.add(InlineKeyboardButton('▶', callback_data='next'))
        await message.answer('Your palettes', reply_markup=markup)

def color_markup(colors):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    return rec_markup([InlineKeyboardButton(color, callback_data=color) for color in colors], markup)

def rec_markup(buttons, markup):
    if len(buttons) <= 3:
        markup.row(*buttons)
        return markup
    else:
        a, b, c = buttons[-1], buttons[-2], buttons[-3]
        markup.row(a, b, c)
        return rec_markup(buttons[:-3], markup)

def clrs(colors):
    return [('#%02x%02x%02x' % (color.rgb.r, color.rgb.g, color.rgb.b)).upper() for color in colors]

def image_to_byte_array(image: Image):
    imgByteArr = BytesIO()
    image.save(imgByteArr, format='PNG')
    return imgByteArr.getvalue()

@dp.callback_query_handler(lambda c: c.data in ['back', 'next'])
async def nb_palette_callback(callback_query: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if 'palindex' not in data.keys() or 'palettes' not in data.keys():
            await callback_query.message.delete()
            await send_palettes(callback_query.message, state)
        else:
            btns = []
            if callback_query.data == 'back':
                if data['palindex'] == 1:
                    btns = [InlineKeyboardButton('▶', callback_data='next')]
                else:
                    btns = [InlineKeyboardButton('◀', callback_data='back'), InlineKeyboardButton('▶', callback_data='next')]
                data['palindex'] -= 1
            elif callback_query.data == 'next':
                if data['palindex'] == len(data['palettes']) - 2:
                    btns = [InlineKeyboardButton('◀', callback_data='back')]
                else:
                    btns = [InlineKeyboardButton('◀', callback_data='back'), InlineKeyboardButton('▶', callback_data='next')]
                data['palindex'] += 1
            markup = color_markup(data['palettes'][data['palindex']])
            markup.add(*btns)
            await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data not in ['save', 'back', 'next'])
async def hex_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'HEX: ' + callback_query.data)

@dp.message_handler(content_types=types.ContentType.TEXT)
async def process_text(message: types.Message):
    await message.answer('I work only with images.')

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
