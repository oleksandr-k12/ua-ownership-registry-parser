#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pyparsing import *
import os.path
import re,sys
import csv
import settings


unicodePrintables = ''.join(chr(c) for c in range(sys.maxunicode) if not chr(c).isspace())
area_regex = r"Загальна площа \(кв\.м\)\: (\d{1,2}[\.,]?\d?)"
apart_num_regex=r"квартира (\d{1,3})"
building_regex=r"будинок \d{1,2}a?"

def sanitize_property_type(prop_type):
  [prop_type, livable]=''.join(prop_type).split(", об'єкт житлової нерухомості:")
  return prop_type.strip()

def sanitize_area(area):
  # print(area)
  if not isinstance(area, str):
    area=' '.join(area)
  matches = re.finditer(area_regex, area)
  for match in matches:
    return match.group(1).replace(',','.')
  return area

def sanitize_address(address):
  address=''.join(address)
  matches = re.finditer(apart_num_regex, address)
  for match in matches:
    return match.group(1)

  return 'нежитл. прим.'

def sanitize_owner(raw_owner):
  ID_NUMBER_LITERAL = ', реєстраційний номер облікової картки платника податків: '
  raw_owner = ' '.join(raw_owner)
  if ID_NUMBER_LITERAL in raw_owner:
    [person, regnum_raw] = raw_owner.split(ID_NUMBER_LITERAL)
  else: 
    [person, regnum_raw] = raw_owner.split(', причина відсутності РНОКПП: ')
  [regnum,citizen] = regnum_raw.split(', країна громадянства: ')
  return (person, regnum, citizen)

def postprocess_owner_basis(raw_basis):
  return ' '.join(raw_basis)

def parse(filename):
  with open(filename, encoding='utf-8') as f:
      data = f.readlines()
  
  data = ''.join(data)
  # these tokens should be suppressed
  NL = LineEnd()
  # like стор. 2 з 206
  page_numbers = Literal('стор.') + Word(nums) + Literal('з')+Word(nums)
  # qrcodes on every page like RRP-4HH2EL59B
  qrcode=Literal("RRP-")+Word(unicodePrintables)

  words = Word(unicodePrintables, unicodePrintables + ' ')
  # useful info start
  DOC_START=Literal('З ДЕРЖАВНОГО РЕЄСТРУ РЕЧОВИХ ПРАВ НА НЕРУХОМЕ МАЙНО')
  DATA_REGISTRY_HEADER=Literal('ВІДОМОСТІ')
  #marks start of second snapshot part of certificate
  SNAPSHOT_REGISTRY_START=Literal('З РЕЄСТРУ ПРАВ ВЛАСНОСТІ НА НЕРУХОМЕ МАЙНО')

  # headers of blocks in actual part of certificate
  AC_HEADER_1 = Literal('Актуальна інформація про об’єкт нерухомого майна')
  AC_HEADER_2 = Literal('Актуальна інформація про право власності')

  RECORD_NUMBER=Literal('Номер запису про право власності / довірчої власності: ')
  DATA_HEADER_OLD_1=Literal('ВІДОМОСТІ ПРО ОБ’ЄКТ НЕРУХОМОГО МАЙНА')
  DATA_HEADER_OLD_2=Literal('ВІДОМОСТІ ПРО ПРАВА ВЛАСНОСТІ')
  STOP_LITERAL_INFO = Literal('Відомості про реєстрацію')
  ADDRESS=Literal('Адреса:')
  NOMOVE_OBJECT=Literal('Об’єкт нерухомого')
  OF_PROPERTY=Literal('майна:')
  SHARE=Literal('Розмір частки: ')
  OBJ_DESCR=Literal('Опис об’єкта: ')

  record_num=RECORD_NUMBER+Word(nums)
  ac_address=ADDRESS+OneOrMore(~AC_HEADER_2+words)('address')
  owner_basis_literal=Literal('Підстава для державної')
  owner_basis_literal_2 = Literal('реєстрації:')
  record_basis=Literal('Підстава внесення')
  owner_basis = ZeroOrMore(~record_basis + words)

  share=SHARE+words('share')

  owner_stop_list = STOP_LITERAL_INFO | RECORD_NUMBER
  owner=Literal('Власники: ') + OneOrMore(~owner_stop_list + words)('owner')
  stop_list=AC_HEADER_1 | record_num | DATA_REGISTRY_HEADER
  trash=ZeroOrMore(~stop_list+words)
  trash_3=ZeroOrMore(~DATA_HEADER_OLD_2+words)
  
  ac_property_type=OneOrMore(~OBJ_DESCR+words)('prop_type')
  # ac_area=AREA+words('area')
  ac_area=OBJ_DESCR + OneOrMore(~ADDRESS +words)('area') 
  
  # property type and address block in snapshot part

  ADDRESS_NOMOVE=Literal('Адреса нерухомого')
  ADDRESS_NOMOVE_2=Literal('майна:')
  PROP_TYPE=Literal('Тип майна:')

  sn_property_type=PROP_TYPE+OneOrMore(~ADDRESS_NOMOVE+words)('prop_type')
  address_stop_list=Literal('Загальна площа') | DATA_HEADER_OLD_2
  sn_address=OneOrMore(~address_stop_list +words)('address')
  
  SN_AREA_START=Literal('Загальна площа')
  sn_area=(SN_AREA_START+words)('area')

  sn_owner=(Literal('ПІБ:')+words('owner'))
  SN_DATE_REGISTRY=Literal('Дата прийняття рішення')
  sn_share=(Literal('Частка власності:')+words('share'))
  SN_EMERSION_REASON=Literal('Підстава виникнення')
  SN_REGISTRATION_MARK=Literal('ВІДМІТКА ПРО РЕЄСТРАЦІЮ')
  SN_REGISTRATION_MARK_DATE=Literal('Дата реєстрації')+words
  DATA_ABSENT=Literal('Відомості про права власності відсутні')

  basis_reason_stop=SN_EMERSION_REASON | DATA_HEADER_OLD_1|SN_REGISTRATION_MARK|SN_DATE_REGISTRY
  basis_mark_stop_list=SN_DATE_REGISTRY|DATA_HEADER_OLD_1
  basis_mark_stop=ZeroOrMore(~basis_mark_stop_list+words)
  
  sh_basis=(SN_EMERSION_REASON+Literal('права власності:')+ZeroOrMore(~basis_reason_stop +words)('basis')+basis_mark_stop)

  ownership_record=Group(record_num+SkipTo(owner_basis_literal+owner_basis_literal_2, include=True)+owner_basis('basis')+record_basis+\
    SkipTo(SHARE)+share+owner+trash)
  
  sn_ownership=Group(SN_DATE_REGISTRY+SkipTo(sn_owner)+sn_owner+SkipTo(sn_share)+sn_share+sh_basis)

  actual_record = Group(AC_HEADER_1+SkipTo(NOMOVE_OBJECT+OF_PROPERTY,include=True)+ac_property_type+ac_area+ac_address+AC_HEADER_2+OneOrMore(ownership_record)('records'))
  
  snapshot_start=DATA_REGISTRY_HEADER.suppress()+SNAPSHOT_REGISTRY_START.suppress()

  snapshot_record=Group(DATA_HEADER_OLD_1+SkipTo(PROP_TYPE)+sn_property_type+SkipTo(ADDRESS_NOMOVE_2,include=True)+sn_address+ZeroOrMore(sn_area)+trash_3+DATA_HEADER_OLD_2+(OneOrMore(sn_ownership)('records')|DATA_ABSENT))

  # grammar = SkipTo(DOC_START, include=True).suppress()+OneOrMore(actual_record)('apartments')+snapshot_start+OneOrMore(snapshot_record)('old')
  grammar = SkipTo(DOC_START, include=True).suppress()+OneOrMore(actual_record)('apartments')

  grammar.ignore(NL)
  grammar.ignore(page_numbers)
  grammar.ignore(qrcode)
  # print ("start")
  result = []
  tokens = grammar.parseString(data, parseAll=True)
  for apt in tokens.apartments:
    print("=================")
    print (sanitize_address(apt.address))
    print (sanitize_property_type(apt.prop_type))
    print (sanitize_area(apt.area))
    for record in apt.records:
      print (sanitize_owner(record.owner))
      print (record.share)
      print (postprocess_owner_basis(record.basis))
  for old_apt in tokens.old:
    print (sanitize_address(old_apt.address))
    print (sanitize_property_type(old_apt.prop_type))
    print (sanitize_area(old_apt.area))
    for record in old_apt.records:
      print (record.owner, record.share)
      test = (" ".join(record.basis).replace('Львівської міської ради','ЛМР').replace('Франківською районною адміністрацією','ФРА').replace('Львівського міського нотаріального округу','ЛМНО').replace('департаменту економічної політики','ДЕП'))
      print (test)
  return tokens

def output_csv(tokens, replacements):
  with open(settings.OUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ('номер', 'тип', 'площа', 'власник', 'ід.номер власника','частка','підстава')
    csv.register_dialect('singlequote',
                     quotechar='',
                     escapechar='|',
                     doublequote = False,
                     quoting=csv.QUOTE_NONE,
                     delimiter='|'
                     )
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, dialect = 'singlequote')

    writer.writeheader()
    for apt in tokens.apartments:
      for record in apt.records:
        row = {}
        row['номер'] = sanitize_address(apt.address)
        row['тип'] = sanitize_property_type(apt.prop_type)
        row['площа'] =  sanitize_area(apt.area)
        person, regnum, citizen = sanitize_owner(record.owner)
        row['власник'] = person
        row ['ід.номер власника'] = regnum
        row['частка'] = record.share
        basis = postprocess_owner_basis(record.basis)
        for k,v in replacements.items():
          basis = basis.replace(k,v)
        row['підстава'] = basis
        writer.writerow(row)

tokens = parse(settings.INPUT_FILE)
output_csv(tokens, settings.REPLACEMENTS)
