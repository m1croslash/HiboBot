from flask import Flask
from threading import Thread
import discord
from discord import app_commands
import os
from datetime import datetime
from dotenv import load_dotenv
import json

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

load_dotenv()

class StaffDatabase:
    def __init__(self, filename='staff_data.json'):
        self.filename = filename
        self.data = self.load_data()
    
    def load_data(self):
        try:
            if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
                # Создаем базовую структуру данных
                base_data = {"employees": {}, "warnings": {}}
                with open(self.filename, 'w', encoding='utf-8') as f:
                    json.dump(base_data, f, ensure_ascii=False, indent=2)
                return base_data
            
            with open(self.filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # Если файл пустой
                    base_data = {"employees": {}, "warnings": {}}
                    with open(self.filename, 'w', encoding='utf-8') as f_write:
                        json.dump(base_data, f_write, ensure_ascii=False, indent=2)
                    return base_data
                
                f.seek(0)
                return json.load(f)
                
        except (json.JSONDecodeError, Exception) as e:
            print(f"❌ Ошибка загрузки данных: {e}. Создаем новую базу данных.")
            # Создаем новую базу данных при ошибке
            base_data = {"employees": {}, "warnings": {}}
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(base_data, f, ensure_ascii=False, indent=2)
            return base_data
    
    def save_data(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения данных: {e}")
    
    def add_employee(self, user_id, name, position, join_date):
        self.data["employees"][str(user_id)] = {
            "name": name,
            "position": position,
            "join_date": join_date,
            "active": True
        }
        self.save_data()
    
    def update_employee(self, user_id, **kwargs):
        if str(user_id) in self.data["employees"]:
            for key, value in kwargs.items():
                self.data["employees"][str(user_id)][key] = value
            self.save_data()
    
    def remove_employee(self, user_id):
        if str(user_id) in self.data["employees"]:
            self.data["employees"][str(user_id)]["active"] = False
            self.save_data()
    
    def get_employee(self, user_id):
        return self.data["employees"].get(str(user_id))
    
    def get_all_employees(self):
        return {uid: data for uid, data in self.data["employees"].items() if data.get("active", True)}
    
    def set_warnings(self, user_id, count):
        self.data["warnings"][str(user_id)] = count
        self.save_data()
    
    def get_warnings(self, user_id):
        return self.data["warnings"].get(str(user_id), 0)
    
    def remove_warnings(self, user_id):
        if str(user_id) in self.data["warnings"]:
            del self.data["warnings"][str(user_id)]
            self.save_data()

class StaffBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.database = StaffDatabase()
    
    async def on_ready(self):
        print(f'✅ {self.user} ready to work!')
        try:
            synced = await self.tree.sync()
            print(f'🔧 Commands synced: {len(synced)}')
        except Exception as e:
            print(f'❌ Error syncing commands: {e}')

    async def send_to_employee_dm(self, employee: discord.Member, embed: discord.Embed):
        try:
            await employee.send(embed=embed)
        except discord.Forbidden:
            print(f"Не удалось отправить сообщение {employee.name} - закрытые ЛС")

    async def auto_dismiss_employee(self, interaction: discord.Interaction, employee: discord.Member):
        employee_data = self.database.get_employee(employee.id)
        start_date = employee_data.get("join_date", employee.joined_at.strftime("%d.%m.%Y")) if employee_data else employee.joined_at.strftime("%d.%m.%Y")
        
        embed = discord.Embed(
            title="🚪 Автоматическое увольнение работника", 
            color=0xff0000,
            description="*Причина: достигнуто максимальное количество выговоров*"
        )
        embed.add_field(name="Работник", value=employee.mention, inline=True)
        embed.add_field(name="Период работы", value=f"{start_date} - {datetime.now().strftime('%d.%m.%Y')}", inline=False)
        embed.add_field(name="Количество выговоров", value="3/3", inline=True)
        embed.set_footer(text="Автоматическое увольнение")
        
        await interaction.followup.send(embed=embed)
        await self.send_to_employee_dm(employee, embed)
        
        self.database.remove_employee(employee.id)
        self.database.remove_warnings(employee.id)
        #удаления роли
        role_ids = [1200579581111959620]
        for role_id in role_ids:
            role = employee.guild.get_role(role_id)
            if role:
                try:
                    await employee.remove_roles(role)
                except:
                    pass

    async def setup_hook(self):
        async def is_guild(interaction: discord.Interaction) -> bool:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "❌ Команды можно использовать только на сервере",
                    ephemeral=True
                )
                return False
            return True

        @self.tree.command(name="добавить_работника", description="Добавляет работника в базу данных")
        @app_commands.describe(employee="Выберите работника", position="Должность работника")
        async def add_employee(interaction: discord.Interaction, employee: discord.Member, position: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            existing_employee = self.database.get_employee(employee.id)
            if existing_employee and existing_employee.get("active", True):
                await interaction.response.send_message("❌ Этот работник уже есть в базе данных", ephemeral=True)
                return
            
            join_date = datetime.now().strftime("%d.%m.%Y")
            self.database.add_employee(employee.id, employee.display_name, position, join_date)
            #Выдача роли работнику
            
            role_ids = [1200579581111959620]
            for role_id in role_ids:
                role = employee.guild.get_role(role_id)
                if role:
                    try:
                        await employee.add_roles(role)
                    except:
                        pass
            
            embed = discord.Embed(title="✅ Работник добавлен в базу", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Должность", value=position, inline=True)
            embed.add_field(name="Дата приема", value=join_date, inline=True)
            embed.set_footer(text=f"Добавил: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)

        @self.tree.command(name="база_работников", description="Показывает список всех работников")
        async def staff_list(interaction: discord.Interaction):
            if not await is_guild(interaction):
                return
                
            employees = self.database.get_all_employees()
            
            if not employees:
                await interaction.response.send_message("📂 База работников пуста", ephemeral=True)
                return
            
            embed = discord.Embed(title="📂 База работников", color=0x00ff00)
            
            for user_id, data in employees.items():
                try:
                    member = await interaction.guild.fetch_member(int(user_id))
                    mention = member.mention
                except:
                    mention = data["name"]
                
                warnings = self.database.get_warnings(int(user_id))
                warn_text = f" ({warnings} выговоров)" if warnings > 0 else ""
                
                embed.add_field(
                    name=f"{data['position']} - {data['name']}", 
                    value=f"{mention}{warn_text}\nПринят: {data['join_date']}", 
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)

        @self.tree.command(name="инфо_работник", description="Информация о работнике")
        @app_commands.describe(employee="Выберите работника")
        async def employee_info(interaction: discord.Interaction, employee: discord.Member):
            if not await is_guild(interaction):
                return
                
            employee_data = self.database.get_employee(employee.id)
            
            if not employee_data or not employee_data.get("active", True):
                await interaction.response.send_message("❌ Этот работник не найден в базе данных", ephemeral=True)
                return
            
            warnings = self.database.get_warnings(employee.id)
            
            embed = discord.Embed(title="📋 Информация о работнике", color=0x00ff00)
            embed.add_field(name="Имя", value=employee.display_name, inline=True)
            embed.add_field(name="Должность", value=employee_data["position"], inline=True)
            embed.add_field(name="Дата приема", value=employee_data["join_date"], inline=True)
            embed.add_field(name="Выговоры", value=f"{warnings}/3", inline=True)
            
            await interaction.response.send_message(embed=embed)

        @self.tree.command(name="выговор", description="Выдает выговор работнику")
        @app_commands.describe(employee="Выберите работника", reason="Причина для выговора")
        async def warn(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles) and interaction.user.id != employee.id:
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            employee_data = self.database.get_employee(employee.id)
            if not employee_data or not employee_data.get("active", True):
                await interaction.response.send_message("❌ Этот работник не найден в базе данных", ephemeral=True)
                return
            
            current_warnings = self.database.get_warnings(employee.id) + 1
            self.database.set_warnings(employee.id, current_warnings)
            
            MAX_WARNINGS = 3
            
            if current_warnings >= MAX_WARNINGS:
                embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
                embed.add_field(name="Работник", value=employee.mention, inline=True)
                embed.add_field(name="Причина", value=reason, inline=False)
                embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
                embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
                
                await interaction.response.send_message(embed=embed)
                await self.send_to_employee_dm(employee, embed)
                
                self.database.remove_warnings(employee.id)
                await self.auto_dismiss_employee(interaction, employee)
                return
            
            embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="снять_выговор", description="Снимает выговор у работника")
        @app_commands.describe(employee="Выберите работника", amount="Количество выговоров для снятия", reason="Причина снятия")
        async def remove_warn(interaction: discord.Interaction, employee: discord.Member, amount: int = 1, reason: str = "Не указана"):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = []
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            current_warnings = self.database.get_warnings(employee.id)
            if current_warnings <= 0:
                await interaction.response.send_message("❌ У этого работника нет выговоров", ephemeral=True)
                return
            
            new_warnings = max(0, current_warnings - amount)
            self.database.set_warnings(employee.id, new_warnings)
            
            if new_warnings == 0:
                warnings_text = "0/3"
            else:
                warnings_text = f"{new_warnings}/3"
            
            embed = discord.Embed(title="✅ Снятие выговора", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Снято выговоров", value=str(amount), inline=True)
            embed.add_field(name="Текущее количество", value=warnings_text, inline=True)
            embed.add_field(name="Причина снятия", value=reason, inline=False)
            embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="зарплата", description="Выплата")  
        @app_commands.describe(employee="Выберите работника", amount="Сумма выплаты", date="Дата выдачи")
        async def salary(interaction: discord.Interaction, employee: discord.Member, amount: str, date: str = None):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            payment_date = date or datetime.now().strftime("%d.%m.%Y")
            embed = discord.Embed(title="💰 Выплата", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Дата выдачи", value=payment_date, inline=True)
            embed.add_field(name="Сумма", value=f"{amount} робуксов", inline=True)
            embed.set_footer(text=f"Выдал: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="увольнение", description="Увольнение работника")
        @app_commands.describe(employee="Выберите работника", reason="Причина увольнения")
        async def dismiss(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            employee_data = self.database.get_employee(employee.id)
            start_date = employee_data.get("join_date", employee.joined_at.strftime("%d.%m.%Y")) if employee_data else employee.joined_at.strftime("%d.%m.%Y")
            
            self.database.remove_employee(employee.id)
            self.database.remove_warnings(employee.id)
            
            embed = discord.Embed(title="🚪 Увольнение работника", color=0xff6b00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Период работы", value=f"{start_date} - {datetime.now().strftime('%d.%m.%Y')}", inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text=f"Уволил: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)
            
            role_ids = [1434494581700825229]
            for role_id in role_ids:
                role = employee.guild.get_role(role_id)
                if role:
                    try:
                        await employee.remove_roles(role)
                    except:
                        pass

        @self.tree.command(name="отпуск", description="Отпуск работника")
        @app_commands.describe(employee="Выберите работника", reason="Причина", duration="Срок отпуска")
        async def vacation(interaction: discord.Interaction, employee: discord.Member, reason: str, duration: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]

            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return

            embed = discord.Embed(title="🏖️ Отпуск работника", color=0x00ffff)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Срок", value=duration, inline=True)
            embed.add_field(name="Дата оформления", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.set_footer(text=f"Оформил: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="тест", description="Проверка бота")
        async def test(interaction: discord.Interaction):
            if not await is_guild(interaction):
                return
            await interaction.response.send_message("✅ Бот работает")

try:
    if os.path.exists('staff_data.json'):
        with open('staff_data.json', 'r') as f:
            content = f.read().strip()
            if not content or content[0] != '{':
                print("⚠️ Обнаружен поврежденный файл данных. Создаем новый...")
                os.remove('staff_data.json')
except:
    pass

bot = StaffBot()
bot.run(os.getenv('TOKEN'))
