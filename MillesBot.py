import discord
from discord import app_commands
import os
from datetime import datetime
from dotenv import load_dotenv
import json
import threading
import time

load_dotenv()

class StaffDatabase:
    def __init__(self, filename='staff_data.json'):
        self.filename = filename
        self.lock = threading.Lock()
        self.data = self.load_data()

    def sanitize_input(self, text: str, max_length: int = 200) -> str:
        if not isinstance(text, str):
            text = str(text)
        text = text.replace('\n', ' ').replace('\r', '').strip()
        text = text[:max_length]
        return text

    def load_data(self):
        base_data = {"employees": {}, "warnings": {}}
        if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
            try:
                with open(self.filename, 'w', encoding='utf-8') as f:
                    json.dump(base_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ Ошибка создания файла: {e}")
            return base_data

        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    with open(self.filename, 'w', encoding='utf-8') as fw:
                        json.dump(base_data, fw, ensure_ascii=False, indent=2)
                    return base_data
                return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка JSON: {e}. Создаю бэкап и новый файл.")
            try:
                backup_name = f"staff_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                try:
                    os.rename(self.filename, backup_name)
                    print(f"💾 Резервная копия создана: {backup_name}")
                except Exception:
                    pass
            except Exception:
                pass
            try:
                with open(self.filename, 'w', encoding='utf-8') as f:
                    json.dump(base_data, f, ensure_ascii=False, indent=2)
            except Exception as e2:
                print(f"❌ Не удалось создать новый файл: {e2}")
            return base_data
        except Exception as e:
            print(f"❌ Ошибка при загрузке: {e}")
            return base_data

    def save_data(self):
        tmp = f"{self.filename}.tmp"
        try:
            with self.lock:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.filename)
        except Exception as e:
            print(f"❌ Ошибка сохранения данных: {e}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except:
                pass
    
    def add_employee(self, user_id, name, position, join_date):
        with self.lock:
            safe_name = self.sanitize_input(name)
            safe_position = self.sanitize_input(position)
            safe_join_date = self.sanitize_input(join_date)

            self.data["employees"][str(user_id)] = {
                "name": safe_name,
                "position": safe_position,
                "join_date": safe_join_date,
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
            print(f'Commands synced: {len(synced)} (from setup_hook)')
        except Exception as e:
            print(f'❌ Error syncing commands in setup_hook: {e}')

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
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112]
            user_roles = [role.id for role in interaction.user.roles]
            
            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
                return
                  
            existing_employee = self.database.get_employee(employee.id)
            if existing_employee and existing_employee.get("active", True):
                await interaction.followup.send("❌ Этот работник уже есть в базе данных", ephemeral=True)
                return
            
            join_date = datetime.now().strftime("%d.%m.%Y")
            self.database.add_employee(employee.id, employee.display_name, position, join_date)

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
            
            await interaction.followup.send(embed=embed)

        @self.tree.command(name="база_работников", description="Показывает список всех работников")
        async def staff_list(interaction: discord.Interaction):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            employees = self.database.get_all_employees()
            
            if not employees:
                await interaction.followup.send("📂 База работников пуста", ephemeral=True)
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
            
            await interaction.followup.send(embed=embed)

        @self.tree.command(name="инфо_работник", description="Информация о работнике")
        @app_commands.describe(employee="Выберите работника")
        async def employee_info(interaction: discord.Interaction, employee: discord.Member):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            employee_data = self.database.get_employee(employee.id)
            if not employee_data or not employee_data.get("active", True):
                await interaction.followup.send("❌ Этот работник не найден в базе данных", ephemeral=True)
                return
            
            warnings = self.database.get_warnings(employee.id)
            
            embed = discord.Embed(title="📋 Информация о работнике", color=0x00ff00)
            embed.add_field(name="Имя", value=employee.display_name, inline=True)
            embed.add_field(name="Должность", value=employee_data["position"], inline=True)
            embed.add_field(name="Дата приема", value=employee_data["join_date"], inline=True)
            embed.add_field(name="Выговоры", value=f"{warnings}/3", inline=True)
            
            await interaction.followup.send(embed=embed)

        @self.tree.command(name="выговор", description="Выдает выговор работнику")
        @app_commands.describe(employee="Выберите работника", reason="Причина для выговора")
        async def warn(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112, 1200579581111959620]
            user_roles = [role.id for role in interaction.user.roles]
            if employee.id == interaction.user.id:
                await interaction.followup.send("❌ Нельзя выдать выговор самому себе!", ephemeral=True)
                return
            
            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
                return
            
            employee_data = self.database.get_employee(employee.id)
            if not employee_data or not employee_data.get("active", True):
                await interaction.followup.send("❌ Этот работник не найден в базе данных", ephemeral=True)
                return
            
            current_warnings = self.database.get_warnings(employee.id) + 1
            self.database.set_warnings(employee.id, current_warnings)
            
            if current_warnings == 1:
                role = employee.guild.get_role(1398751720665780324)
                if role:
                    await employee.add_roles(role)
            
            MAX_WARNINGS = 3
            
            if current_warnings >= MAX_WARNINGS:
                embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
                embed.add_field(name="Работник", value=employee.mention, inline=True)
                embed.add_field(name="Причина", value=reason, inline=False)
                embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
                embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
                
                await interaction.followup.send(embed=embed)
                await self.send_to_employee_dm(employee, embed)
                
                self.database.remove_warnings(employee.id)
                await self.auto_dismiss_employee(interaction, employee)
                return
            
            embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
            
            await interaction.followup.send(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="снять_выговор", description="Снимает выговор у работника")
        @app_commands.describe(employee="Выберите работника", amount="Количество выговоров для снятия", reason="Причина снятия")
        async def remove_warn(interaction: discord.Interaction, employee: discord.Member, amount: int = 1, reason: str = "Не указана"):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112]
            user_roles = [role.id for role in interaction.user.roles]
            
            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
                return
            
            current_warnings = self.database.get_warnings(employee.id)
            if current_warnings <= 0:
                await interaction.followup.send("❌ У этого работника нет выговоров", ephemeral=True)
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
            
            await interaction.followup.send(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="зарплата", description="Выплата")  
        @app_commands.describe(employee="Выберите работника", amount="Сумма выплаты", date="Дата выдачи")
        async def salary(interaction: discord.Interaction, employee: discord.Member, amount: str, date: str = None):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112]
            user_roles = [role.id for role in interaction.user.roles]
            
            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
                return
       
            payment_date = date or datetime.now().strftime("%d.%m.%Y")
            embed = discord.Embed(title="💰 Выплата", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Дата выдачи", value=payment_date, inline=True)
            embed.add_field(name="Сумма", value=f"{amount} робуксов", inline=True)
            embed.set_footer(text=f"Выдал: {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="увольнение", description="Увольнение работника")
        @app_commands.describe(employee="Выберите работника", reason="Причина увольнения")
        async def dismiss(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112]
            user_roles = [role.id for role in interaction.user.roles]
            
            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
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
            
            await interaction.followup.send(embed=embed)
            await self.send_to_employee_dm(employee, embed)
            
            role_ids = [1200579581111959620]
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
            
            await interaction.response.defer()
                
            allowed_roles_ids = [1200579581149712416, 1200579581149712417, 1200579581149712415, 1200579581128749114, 1200579581128749113, 1402693590655963156, 1200579581128749112]
            user_roles = [role.id for role in interaction.user.roles]

            has_allowed = any(r in allowed_roles_ids for r in user_roles)
            is_admin = getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator
            if not (has_allowed or is_admin):
                await interaction.followup.send("❌ Недостаточно прав", ephemeral=True)
                return

            embed = discord.Embed(title="🏖️ Отпуск работника", color=0x00ffff)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Срок", value=duration, inline=True)
            embed.add_field(name="Дата оформления", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.set_footer(text=f"Оформил: {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="тест", description="Проверка бота")
        async def test(interaction: discord.Interaction):
            if interaction.guild is None:
                await interaction.response.send_message("❌ Команды можно использовать только на сервере", ephemeral=True)
                return
            
            await interaction.followup.send("✅ Бот работает")

token = os.getenv('TOKEN')
if not token:
    raise RuntimeError("TOKEN env var is not set. Set TOKEN in env before running the bot")
bot = StaffBot()
bot.run(token)
